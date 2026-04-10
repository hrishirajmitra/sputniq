from __future__ import annotations

import hashlib
import json
import logging
import re
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


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _service_name(app_slug: str, service_id: str) -> str:
    return f"sputniq-{app_slug}-{service_id}"


def _runtime_network_name(app_slug: str) -> str:
    return f"sputniq-runtime-{app_slug}"


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


def _wait_for_container(client: docker.DockerClient, container_name: str, timeout_s: float = 18.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_status = "created"

    while time.monotonic() < deadline:
        container = client.containers.get(container_name)
        container.reload()
        last_status = container.status

        if last_status == "running":
            return

        if last_status in {"dead", "exited"}:
            logs = container.logs(tail=80).decode("utf-8", errors="replace").strip()
            raise DeploymentError(
                f"Service '{container_name}' exited during startup."
                + (f"\n{logs}" if logs else "")
            )

        time.sleep(0.5)

    raise DeploymentError(
        f"Service '{container_name}' did not reach a running state within {timeout_s:.0f}s "
        f"(last status: {last_status})."
    )


def _artifact_bundle(manifest: dict[str, Any], config: Any) -> dict[str, Any]:
    manifest_blob = json.dumps(manifest, sort_keys=True).encode("utf-8")
    config_blob = json.dumps(config.model_dump(), sort_keys=True).encode("utf-8")
    config_hash = hashlib.sha256(config_blob).hexdigest()
    bundle_id = hashlib.sha256(manifest_blob).hexdigest()[:12]

    return {
        "bundle_id": f"b-{bundle_id}",
        "version": str(config.platform.version),
        "config_hash": f"sha256:{config_hash}",
        "built_at": manifest["built_at"],
        "services": {
            service_id: {
                "image": f"{config.platform.namespace}/{service_id}:{config.platform.version}",
                "digest": f"sha256:{hashlib.sha256(service_id.encode('utf-8')).hexdigest()}",
            }
            for service_id in manifest["services"]
        },
        "signature": "unsigned-local-build",
    }


def _build_service_records(config: Any, manifest: dict[str, Any], client: docker.DockerClient) -> list[dict[str, Any]]:
    services = manifest["services"]
    ports = _allocate_ports(client, len(services))
    tool_map = _tool_entrypoints(config)
    agents = {agent.id: agent for agent in config.agents}
    tools = {tool.id: tool for tool in config.tools}
    records: list[dict[str, Any]] = []

    for port, (service_id, service_meta) in zip(ports, services.items(), strict=True):
        logical_id = service_meta["logical_id"]
        kind = service_meta["kind"]

        if kind == "agent":
            agent = agents[logical_id]
            model_id = agent.model
            entrypoint = agent.entrypoint
            tool_entrypoints = {tool_id: tool_map[tool_id] for tool_id in agent.tools if tool_id in tool_map}
            service_role = "agent"
        elif kind == "tool":
            model_id = None
            entrypoint = tools[logical_id].entrypoint
            tool_entrypoints = tool_map
            service_role = "tool"
        else:
            model_id = None
            entrypoint = ""
            tool_entrypoints = tool_map
            service_role = logical_id

        records.append(
            {
                "id": service_id,
                "logical_id": logical_id,
                "kind": kind,
                "plane": service_meta["plane"],
                "service_role": service_role,
                "entrypoint": entrypoint,
                "tag": f"{config.platform.namespace}/{service_id}:{config.platform.version}",
                "port": port,
                "model_id": model_id,
                "tool_entrypoints": tool_entrypoints,
            }
        )

    return records


def _service_maps(records: list[dict[str, Any]], app_slug: str) -> tuple[dict[str, str], dict[str, str]]:
    app_service_urls = {
        record["logical_id"]: f"http://{_service_name(app_slug, record['id'])}:{record['port']}"
        for record in records
        if record["kind"] in {"agent", "tool"}
    }
    platform_urls = {
        record["logical_id"]: f"http://{_service_name(app_slug, record['id'])}:{record['port']}"
        for record in records
        if record["kind"] == "platform"
    }
    return app_service_urls, platform_urls


def _ensure_network(client: docker.DockerClient, network_name: str) -> docker.models.networks.Network:
    try:
        return client.networks.get(network_name)
    except docker.errors.NotFound:
        return client.networks.create(network_name, driver="bridge")


def deploy_app(config: Any, extract_dir: Path) -> list[dict[str, Any]]:
    client = docker.from_env()
    build_dir = extract_dir / ".agentos" / "build"
    app_slug = _slug(config.platform.name)
    runtime_network_name = _runtime_network_name(app_slug)
    runtime_network = _ensure_network(client, runtime_network_name)

    try:
        control_network = client.networks.get("sputniq-control")
        kafka_bootstrap_servers = "kafka:29092"
    except docker.errors.NotFound:
        control_network = None
        kafka_bootstrap_servers = "localhost:9092"

    manifest = generate_build_artifacts(config, build_dir)
    artifact_bundle = _artifact_bundle(manifest, config)
    builder = ImageBuilder()
    services = _build_service_records(config, manifest, client)
    app_service_urls, platform_urls = _service_maps(services, app_slug)
    tool_schemas = json.loads((build_dir / manifest["tool_schema_registry"]).read_text("utf-8"))
    message_schemas = json.loads((build_dir / manifest["message_schema_registry"]).read_text("utf-8"))
    started_names: list[str] = []

    try:
        logger.info("Starting deployment for %s", config.platform.name)

        for service in services:
            service_dir = build_dir / "services" / service["id"]
            if service["kind"] in {"agent", "tool"}:
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
                    "logical_id": service["logical_id"],
                    "service_kind": service["kind"],
                    "service_role": service["service_role"],
                    "entrypoint": service["entrypoint"],
                    "app_name": config.platform.name,
                    "namespace": config.platform.namespace,
                    "version": config.platform.version,
                    "port": service["port"],
                    "plane": service["plane"],
                    "model_id": service["model_id"],
                    "tool_entrypoints": service["tool_entrypoints"],
                    "workflow_ids": [workflow.id for workflow in config.workflows],
                    "app_service_urls": app_service_urls,
                    "platform_urls": platform_urls,
                    "manifest": manifest,
                    "artifact_bundle": artifact_bundle,
                    "workflows": [workflow.model_dump() for workflow in config.workflows],
                    "tools": [tool.model_dump(by_alias=True) for tool in config.tools],
                    "models": [model.model_dump() for model in config.models],
                    "agents": [agent.model_dump() for agent in config.agents],
                    "tool_schemas": tool_schemas,
                    "message_schemas": message_schemas,
                    "default_workflow_id": config.workflows[0].id if config.workflows else None,
                },
            )

            builder.build_service(service_dir, service["tag"])

        for service in services:
            container_name = _service_name(app_slug, service["id"])
            labels = {
                "sputniq.managed": "true",
                "sputniq.app_name": config.platform.name,
                "sputniq.namespace": config.platform.namespace,
                "sputniq.version": str(config.platform.version),
                "sputniq.service_id": service["id"],
                "sputniq.logical_id": service["logical_id"],
                "sputniq.service_kind": service["kind"],
                "sputniq.service_role": service["service_role"],
                "sputniq.plane": service["plane"],
                "sputniq.service_port": str(service["port"]),
                "sputniq.health_path": "/health",
                "sputniq.chat_path": "/api/chat" if service["service_role"] == "gateway" else "",
                "sputniq.chat_ready": "true" if service["service_role"] == "gateway" else "false",
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
                hostname=container_name,
                network=runtime_network_name,
                ports={f"{service['port']}/tcp": service["port"]},
                labels=labels,
                environment={
                    "KAFKA_BOOTSTRAP_SERVERS": kafka_bootstrap_servers,
                    "SPUTNIQ_SERVICE_ID": service["id"],
                    "SPUTNIQ_SERVICE_PORT": str(service["port"]),
                    "SPUTNIQ_SERVICE_ROLE": service["service_role"],
                },
            )

            if control_network is not None:
                control_network.connect(container_name)

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
        try:
            runtime_network.reload()
            if not runtime_network.containers:
                runtime_network.remove()
        except docker.errors.DockerException:
            logger.warning("Could not remove runtime network %s", runtime_network_name)
        if isinstance(exc, DeploymentError):
            raise
        raise DeploymentError(str(exc)) from exc
