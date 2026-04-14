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
    entrypoint: str,
    config: SputniqConfig,
    service_dir: Path,
) -> None:
    """Render Dockerfile, service.yaml, and requirements.txt for one service."""
    service_dir.mkdir(parents=True, exist_ok=True)

    ctx = {
        "service_id": service_id,
        "module_path": _module_from_entrypoint(entrypoint),
        "namespace": config.platform.namespace,
        "version": config.platform.version,
        "runtime": config.platform.runtime,
        "secrets": config.infrastructure.secrets,
        "extra_deps": [],
    }

    for tmpl_name, out_name in [
        ("Dockerfile.j2", "Dockerfile"),
        ("service.yaml.j2", "service.yaml"),
        ("requirements.txt.j2", "requirements.txt"), ("run_worker.py.j2", "run_worker.py"),
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

    service_ids: list[str] = []

    for agent in config.agents:
        _render_service(env, agent.id, agent.entrypoint, config, services_dir / agent.id)
        service_ids.append(agent.id)

    for tool in config.tools:
        _render_service(env, tool.id, tool.entrypoint, config, services_dir / tool.id)
        service_ids.append(tool.id)

    # Generate Dockerfile for workflows
    for workflow in getattr(config, "workflows", []):
        wf_dir = services_dir / workflow.id
        wf_dir.mkdir(parents=True, exist_ok=True)
        dockerfile = "FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\nCOPY . .\nCMD [\"python\", \"run.py\"]\n"
        (wf_dir / "Dockerfile").write_text(dockerfile, "utf-8")
        
        ctx = {"extra_deps": []}
        rendered = env.get_template("requirements.txt.j2").render(ctx)
        (wf_dir / "requirements.txt").write_text(rendered, "utf-8")
        
        service_ids.append(workflow.id)

    # Write tool schemas
    tool_schemas = {
        t.id: t.schema_def.model_dump() for t in config.tools
    }
    (schemas_dir / "tool-schemas.json").write_text(
        json.dumps(tool_schemas, indent=2), "utf-8"
    )

    manifest = _generate_manifest(config, service_ids)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")

    return manifest


def _generate_manifest(config: SputniqConfig, service_ids: list[str]) -> dict:
    """Build the build manifest dictionary."""
    return {
        "platform": config.platform.name,
        "version": config.platform.version,
        "namespace": config.platform.namespace,
        "built_at": datetime.now(UTC).isoformat(),
        "services": {sid: {"id": sid} for sid in service_ids},
        "workflows": [w.id for w in config.workflows],
    }
