"""Service artifact generator — builds .agentos/build/ from a SputniqConfig."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sputniq.models.messages import (
    AgentInput,
    AgentOutput,
    Error,
    HeartBeat,
    ModelRequest,
    ModelResponse,
    ToolRequest,
    ToolResponse,
    WorkflowComplete,
    WorkflowStepMessage,
)
from sputniq.models.platform import SputniqConfig

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_PLATFORM_SERVICE_SPECS = [
    {"logical_id": "gateway", "plane": "data-plane"},
    {"logical_id": "workflow-coordinator", "plane": "control-plane"},
    {"logical_id": "tool-dispatcher", "plane": "data-plane"},
    {"logical_id": "model-proxy", "plane": "data-plane"},
    {"logical_id": "schema-registry", "plane": "control-plane"},
    {"logical_id": "artifact-store", "plane": "control-plane"},
    {"logical_id": "build-controller", "plane": "control-plane"},
]


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _module_from_entrypoint(entrypoint: str) -> str:
    """Convert 'src/agents/foo.py:Bar' -> 'src.agents.foo'."""
    file_part = entrypoint.split(":")[0]
    return file_part.replace("/", ".").removesuffix(".py")


def _service_context(config: SputniqConfig, service_id: str, *, runner_file: str) -> dict:
    return {
        "service_id": service_id,
        "namespace": config.platform.namespace,
        "version": config.platform.version,
        "runtime": config.platform.runtime,
        "secrets": config.infrastructure.secrets,
        "runner_file": runner_file,
        "extra_deps": [
            "httpx>=0.28.0",
            "prometheus-client>=0.19.0",
        ],
    }


def _render_application_service(
    env: Environment,
    service_id: str,
    entrypoint: str,
    config: SputniqConfig,
    service_dir: Path,
) -> None:
    service_dir.mkdir(parents=True, exist_ok=True)
    ctx = _service_context(config, service_id, runner_file=".sputniq_service_runner.py")
    ctx["module_path"] = _module_from_entrypoint(entrypoint)

    for tmpl_name, out_name in [
        ("Dockerfile.j2", "Dockerfile"),
        ("service.yaml.j2", "service.yaml"),
        ("requirements.txt.j2", "requirements.txt"),
        ("service_runner.py.j2", ".sputniq_service_runner.py"),
    ]:
        rendered = env.get_template(tmpl_name).render(ctx)
        (service_dir / out_name).write_text(rendered, "utf-8")


def _render_platform_service(
    env: Environment,
    service_id: str,
    config: SputniqConfig,
    service_dir: Path,
) -> None:
    service_dir.mkdir(parents=True, exist_ok=True)
    ctx = _service_context(config, service_id, runner_file=".sputniq_platform_runner.py")

    for tmpl_name, out_name in [
        ("Dockerfile.j2", "Dockerfile"),
        ("service.yaml.j2", "service.yaml"),
        ("requirements.txt.j2", "requirements.txt"),
        ("platform_runner.py.j2", ".sputniq_platform_runner.py"),
    ]:
        rendered = env.get_template(tmpl_name).render(ctx)
        (service_dir / out_name).write_text(rendered, "utf-8")


def generate_build_artifacts(config: SputniqConfig, output_dir: Path) -> dict:
    """Generate the full .agentos/build/ tree from a validated config.

    Returns the build manifest dict.
    """
    env = _jinja_env()
    services_dir = output_dir / "services"
    schemas_dir = output_dir / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)

    app_services: list[dict[str, str]] = []
    platform_services: list[dict[str, str]] = []
    app_prefix = _slug(config.platform.name)

    for agent in config.agents:
        _render_application_service(env, agent.id, agent.entrypoint, config, services_dir / agent.id)
        app_services.append(
            {
                "id": agent.id,
                "logical_id": agent.id,
                "kind": "agent",
                "plane": "data-plane",
                "entrypoint": agent.entrypoint,
            }
        )

    for tool in config.tools:
        _render_application_service(env, tool.id, tool.entrypoint, config, services_dir / tool.id)
        app_services.append(
            {
                "id": tool.id,
                "logical_id": tool.id,
                "kind": "tool",
                "plane": "data-plane",
                "entrypoint": tool.entrypoint,
            }
        )

    for spec in _PLATFORM_SERVICE_SPECS:
        service_id = f"{app_prefix}-{spec['logical_id']}"
        _render_platform_service(env, service_id, config, services_dir / service_id)
        platform_services.append(
            {
                "id": service_id,
                "logical_id": spec["logical_id"],
                "kind": "platform",
                "plane": spec["plane"],
                "entrypoint": "",
            }
        )

    _write_tool_schemas(config, schemas_dir)
    _write_message_schemas(schemas_dir)

    manifest = _generate_manifest(config, app_services, platform_services)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")

    return manifest


def _write_tool_schemas(config: SputniqConfig, schemas_dir: Path) -> None:
    tool_schemas = {tool.id: tool.schema_def.model_dump() for tool in config.tools}
    (schemas_dir / "tool-schemas.json").write_text(json.dumps(tool_schemas, indent=2), "utf-8")


def _write_message_schemas(schemas_dir: Path) -> None:
    message_models = {
        "AgentInput": AgentInput,
        "AgentOutput": AgentOutput,
        "ToolRequest": ToolRequest,
        "ToolResponse": ToolResponse,
        "ModelRequest": ModelRequest,
        "ModelResponse": ModelResponse,
        "WorkflowStepMessage": WorkflowStepMessage,
        "WorkflowComplete": WorkflowComplete,
        "Error": Error,
        "HeartBeat": HeartBeat,
    }
    payload = {
        model_name: model.model_json_schema()
        for model_name, model in message_models.items()
    }
    (schemas_dir / "message-schemas.json").write_text(json.dumps(payload, indent=2), "utf-8")


def _generate_manifest(
    config: SputniqConfig,
    app_services: list[dict[str, str]],
    platform_services: list[dict[str, str]],
) -> dict:
    services = app_services + platform_services
    return {
        "platform": config.platform.name,
        "version": config.platform.version,
        "namespace": config.platform.namespace,
        "built_at": datetime.now(UTC).isoformat(),
        "services": {
            service["id"]: {
                "id": service["id"],
                "logical_id": service["logical_id"],
                "kind": service["kind"],
                "plane": service["plane"],
                "entrypoint": service["entrypoint"],
            }
            for service in services
        },
        "workflows": [workflow.id for workflow in config.workflows],
        "tool_schema_registry": "schemas/tool-schemas.json",
        "message_schema_registry": "schemas/message-schemas.json",
    }
