"""Service artifact generator — builds .agentos/build/ from a SputniqConfig."""

import json
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sputniq.models.platform import SputniqConfig

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def _module_from_entrypoint(entrypoint: str) -> str:
    """Convert 'src/agents/foo.py:Bar' -> 'src.agents.foo'."""
    file_part = entrypoint.split(":")[0]
    return file_part.replace("/", ".").removesuffix(".py")


def _render_service(
    env: Environment,
    service_id: str,
    service_type: str,
    entrypoint: str,
    runtime_lang: str,
    config: SputniqConfig,
    service_dir: Path,
) -> None:
    """Render Dockerfile, service.yaml, and requirements.txt for one service."""
    service_dir.mkdir(parents=True, exist_ok=True)

    ctx = {
        "service_id": service_id,
        "service_type": service_type,
        "entrypoint": entrypoint,
        "module_path": _module_from_entrypoint(entrypoint),
        "runtime_lang": runtime_lang,
        "namespace": config.platform.namespace,
        "version": config.platform.version,
        "runtime": config.platform.runtime,
        "secrets": config.infrastructure.secrets,
        "extra_deps": [
            "fastapi>=0.110.0",
            "uvicorn>=0.29.0",
            "requests",
            "pydantic>=2.0",
            "click>=8.0",
            "jinja2>=3.0",
            "rich>=13.0",
            "aiokafka>=0.11.0",
            "redis>=5.0.0",
            "asyncpg>=0.29.0",
            "docker>=7.0.0",
            "opentelemetry-api>=1.20.0",
            "opentelemetry-sdk>=1.20.0",
            "opentelemetry-exporter-otlp>=1.20.0",
            "prometheus-client>=0.19.0",
            "python-jose[cryptography]>=3.3.0",
            "langgraph>=0.0.30",
            "python-multipart>=0.0.9"
        ],
    }

    templates = [
        ("Dockerfile.j2", "Dockerfile"),
        ("service.yaml.j2", "service.yaml"),
    ]
    if runtime_lang == "python":
        templates.append(("requirements.txt.j2", "requirements.txt"))
    elif runtime_lang == "node":
        pass  # Handle package.json logic if necessary in the future

    for tmpl_name, out_name in templates:
        rendered = env.get_template(tmpl_name).render(ctx)
        (service_dir / out_name).write_text(rendered, "utf-8")


def _generate_linux_prereqs(output_dir: Path) -> None:
    """Generate vanilla Linux installation scripts."""
    install_sh = """#!/bin/bash
set -e

echo "Ensuring Linux Pre-requisites for Sputniq Deployment..."

if [ -x "$(command -v apt-get)" ]; then
    sudo apt-get update
    sudo apt-get install -y python3.11 python3.11-venv curl docker.io docker-compose-v2
elif [ -x "$(command -v yum)" ]; then
    sudo yum update -y
    sudo yum install -y python3 curl docker
    # Amazon Linux / CentOS specifics omitted for brevity
fi

echo "Pre-requisites installed successfully."
"""
    (output_dir / "install.sh").write_text(install_sh, "utf-8")
    (output_dir / "install.sh").chmod(0o755)


def generate_build_artifacts(config: SputniqConfig, output_dir: Path) -> dict:
    """Generate the full .agentos/build/ tree from a validated config.

    Returns the build manifest dict.
    """
    env = _jinja_env()
    services_dir = output_dir / "services"
    schemas_dir = output_dir / "schemas"
    graphs_dir = output_dir / "orchestrations"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir.mkdir(parents=True, exist_ok=True)

    _generate_linux_prereqs(output_dir)

    services: dict[str, dict[str, str]] = {}

    for agent in config.agents:
        _render_service(
            env,
            agent.id,
            "agent",
            agent.entrypoint,
            agent.runtime,
            config,
            services_dir / agent.id,
        )
        services[agent.id] = {"id": agent.id, "type": "agent", "runtime": agent.runtime}

    for tool in config.tools:
        _render_service(
            env,
            tool.id,
            "tool",
            tool.entrypoint,
            tool.runtime,
            config,
            services_dir / tool.id,
        )
        services[tool.id] = {"id": tool.id, "type": "tool", "runtime": tool.runtime}

    tool_schemas = {tool.id: tool.schema_def.model_dump() for tool in config.tools}
    (schemas_dir / "tool-schemas.json").write_text(
        json.dumps(tool_schemas, indent=2), "utf-8"
    )
    model_endpoints = {
        model.id: {
            "provider": model.provider,
            "endpoint": model.endpoint,
            "capabilities": model.capabilities,
            "config": model.config,
        }
        for model in config.models
    }
    (schemas_dir / "model-endpoints.json").write_text(
        json.dumps(model_endpoints, indent=2), "utf-8"
    )
    orchestration_graphs = {
        orchestration.id: orchestration.model_dump(mode="json")
        for orchestration in config.orchestrations
    }
    (graphs_dir / "graphs.json").write_text(
        json.dumps(orchestration_graphs, indent=2), "utf-8"
    )

    manifest = _generate_manifest(config, services)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")

    return manifest


def _generate_manifest(config: SputniqConfig, services: dict[str, dict[str, str]]) -> dict:
    """Build the build manifest dictionary."""
    return {
        "platform": config.platform.name,
        "version": config.platform.version,
        "namespace": config.platform.namespace,
        "built_at": datetime.now(UTC).isoformat(),
        "entities": {
            "agents": [agent.id for agent in config.agents],
            "tools": [tool.id for tool in config.tools],
            "models": [model.id for model in config.models],
            "orchestrations": [
                orchestration.id for orchestration in config.orchestrations
            ],
        },
        "services": services,
        "orchestrations": [orchestration.id for orchestration in config.orchestrations],
        "workflows": [orchestration.id for orchestration in config.orchestrations],
    }
