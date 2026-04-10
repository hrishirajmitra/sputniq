import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

import docker

from sputniq.generator.engine import generate_build_artifacts
from sputniq.ops.builder import ImageBuilder

logger = logging.getLogger(__name__)


class DeploymentError(RuntimeError):
    """Raised when a deployment cannot be completed successfully."""


def _service_name(service_id: str) -> str:
    return f"sputniq-{service_id}"


def _tool_entrypoints(config: Any) -> dict[str, str]:
    return {tool.id: tool.entrypoint for tool in config.tools}


def _used_ports(client: docker.DockerClient) -> set[int]:
    ports: set[int] = set()
    for container in client.containers.list(all=True, filters={"label": "sputniq.managed=true"}):
        port_value = container.labels.get("sputniq.service_port")
        if not port_value:
            continue
        try:
            ports.add(int(port_value))
        except ValueError:
            logger.warning("Ignoring invalid service port label %r on %s", port_value, container.name)
    return ports


def _allocate_ports(client: docker.DockerClient, count: int, start: int = 8100) -> list[int]:
    used = _used_ports(client)
    allocated: list[int] = []
    candidate = start

    while len(allocated) < count:
        if candidate not in used:
            allocated.append(candidate)
            used.add(candidate)
        candidate += 1

    return allocated


def _write_service_definition(service_dir: Path, payload: dict[str, Any]) -> None:
    (service_dir / ".sputniq_service.json").write_text(
        json.dumps(payload, indent=2),
        "utf-8",
    )


def _wait_for_container(client: docker.DockerClient, container_name: str, timeout_s: float = 12.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_status = "created"

    while time.monotonic() < deadline:
        container = client.containers.get(container_name)
        container.reload()
        last_status = container.status

        if last_status == "running":
            return

        if last_status in {"dead", "exited"}:
            logs = container.logs(tail=60).decode("utf-8", errors="replace").strip()
            raise DeploymentError(
                f"Service '{container_name}' exited during startup."
                + (f"\n{logs}" if logs else "")
            )

        time.sleep(0.5)

    raise DeploymentError(
        f"Service '{container_name}' did not reach a running state within {timeout_s:.0f}s "
        f"(last status: {last_status})."
    )


def _build_service_records(config: Any, client: docker.DockerClient) -> list[dict[str, Any]]:
    ports = _allocate_ports(client, len(config.agents) + len(config.tools))
    tool_map = _tool_entrypoints(config)
    services: list[dict[str, Any]] = []
    port_iter = iter(ports)

    for agent in config.agents:
        services.append(
            {
                "id": agent.id,
                "kind": "agent",
                "entrypoint": agent.entrypoint,
                "tag": f"{config.platform.namespace}/{agent.id}:{config.platform.version}",
                "port": next(port_iter),
                "model_id": agent.model,
                "tool_entrypoints": {
                    tool_id: tool_map[tool_id]
                    for tool_id in agent.tools
                    if tool_id in tool_map
                },
            }
        )

    for tool in config.tools:
        services.append(
            {
                "id": tool.id,
                "kind": "tool",
                "entrypoint": tool.entrypoint,
                "tag": f"{config.platform.namespace}/{tool.id}:{config.platform.version}",
                "port": next(port_iter),
                "model_id": None,
                "tool_entrypoints": tool_map,
            }
        )

    return services


def deploy_app(config: Any, extract_dir: Path) -> list[dict[str, Any]]:
    client = docker.from_env()
    build_dir = extract_dir / ".agentos" / "build"
    manifest = generate_build_artifacts(config, build_dir)
    builder = ImageBuilder()
    services = _build_service_records(config, client)
    started_names: list[str] = []

    try:
        logger.info("Starting deployment for %s", config.platform.name)

        for service in services:
            service_dir = build_dir / "services" / service["id"]
            shutil.copytree(
                extract_dir,
                service_dir,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".agentos"),
            )

            _write_service_definition(
                service_dir,
                {
                    "service_id": service["id"],
                    "service_kind": service["kind"],
                    "entrypoint": service["entrypoint"],
                    "app_name": config.platform.name,
                    "namespace": config.platform.namespace,
                    "version": config.platform.version,
                    "port": service["port"],
                    "model_id": service["model_id"],
                    "tool_entrypoints": service["tool_entrypoints"],
                    "workflow_ids": [workflow.id for workflow in config.workflows],
                    "manifest_services": sorted(manifest["services"].keys()),
                },
            )

            builder.build_service(service_dir, service["tag"])

        for service in services:
            container_name = _service_name(service["id"])
            labels = {
                "sputniq.managed": "true",
                "sputniq.app_name": config.platform.name,
                "sputniq.namespace": config.platform.namespace,
                "sputniq.version": str(config.platform.version),
                "sputniq.service_id": service["id"],
                "sputniq.service_kind": service["kind"],
                "sputniq.service_port": str(service["port"]),
                "sputniq.health_path": "/health",
                "sputniq.chat_path": "/api/chat" if service["kind"] == "agent" else "",
                "sputniq.chat_ready": "true" if service["kind"] == "agent" else "false",
                "sputniq.workflow_ids": json.dumps([workflow.id for workflow in config.workflows]),
            }

            try:
                existing = client.containers.get(container_name)
                existing.remove(force=True)
                logger.info("Removed previous container %s", container_name)
            except docker.errors.NotFound:
                pass

            client.containers.run(
                image=service["tag"],
                name=container_name,
                detach=True,
                network_mode="host",
                labels=labels,
                environment={
                    "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
                    "SPUTNIQ_SERVICE_ID": service["id"],
                    "SPUTNIQ_SERVICE_PORT": str(service["port"]),
                },
            )
            started_names.append(container_name)

        for container_name in started_names:
            _wait_for_container(client, container_name)

        logger.info("Deployment completed successfully for %s", config.platform.name)
        return services
    except Exception as exc:
        logger.error("Deployment failed: %s", exc, exc_info=True)
        for container_name in started_names:
            try:
                client.containers.get(container_name).remove(force=True)
            except docker.errors.DockerException:
                logger.warning("Could not remove failed container %s", container_name)
        if isinstance(exc, DeploymentError):
            raise
        raise DeploymentError(str(exc)) from exc
