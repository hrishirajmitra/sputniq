import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import docker
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from sputniq.config.errors import ConfigError
from sputniq.config.parser import detect_cycles, load_config, resolve_references
from sputniq.models.tools import ToolDefinition
from sputniq.models.workflows import WorkflowDefinition
from sputniq.ops.deploy import DeploymentError, deploy_app

app = FastAPI(title="Sputniq AgentOS Control API", version="0.1.0")

_workflows: dict[str, WorkflowDefinition] = {}
_tools: dict[str, ToolDefinition] = {}
_UI_DIR = Path(__file__).resolve().parent


class RegistryResponse(BaseModel):
    status: str
    count: int


def _load_ui_asset(name: str) -> str:
    return (_UI_DIR / name).read_text("utf-8")


def _parse_json_label(value: str | None) -> Any:
    if not value:
        return []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []


def _managed_container_payload(container: Any) -> dict[str, Any]:
    labels = container.labels
    port = labels.get("sputniq.service_port")

    return {
        "id": container.short_id,
        "name": container.name,
        "service_id": labels.get("sputniq.service_id", container.name.removeprefix("sputniq-")),
        "service_kind": labels.get("sputniq.service_kind", "unknown"),
        "status": container.status,
        "image": container.image.tags[0] if container.image.tags else "unknown",
        "app_name": labels.get("sputniq.app_name"),
        "namespace": labels.get("sputniq.namespace"),
        "version": labels.get("sputniq.version"),
        "port": int(port) if port and port.isdigit() else None,
        "health_path": labels.get("sputniq.health_path", "/health"),
        "chat_path": labels.get("sputniq.chat_path") or None,
        "chat_ready": labels.get("sputniq.chat_ready") == "true",
        "workflow_ids": _parse_json_label(labels.get("sputniq.workflow_ids")),
        "logs_cmd": f"docker logs -f {container.name}",
    }


@app.post("/api/v1/registry/workflows", response_model=RegistryResponse)
async def register_workflow(workflow: WorkflowDefinition) -> RegistryResponse:
    _workflows[workflow.id] = workflow
    return RegistryResponse(status="registered", count=len(_workflows))


@app.get("/api/v1/registry/workflows", response_model=list[WorkflowDefinition])
async def list_workflows() -> list[WorkflowDefinition]:
    return list(_workflows.values())


@app.get("/api/v1/registry/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(workflow_id: str) -> WorkflowDefinition:
    if workflow_id not in _workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _workflows[workflow_id]


@app.post("/api/v1/registry/tools", response_model=RegistryResponse)
async def register_tool(tool: ToolDefinition) -> RegistryResponse:
    _tools[tool.id] = tool
    return RegistryResponse(status="registered", count=len(_tools))


@app.get("/api/v1/registry/tools", response_model=list[ToolDefinition])
async def list_tools() -> list[ToolDefinition]:
    return list(_tools.values())


@app.get("/api/v1/registry/tools/{tool_id}", response_model=ToolDefinition)
async def get_tool(tool_id: str) -> ToolDefinition:
    if tool_id not in _tools:
        raise HTTPException(status_code=404, detail="Tool not found")
    return _tools[tool_id]


@app.get("/api/v1/registry/deployments")
async def list_deployments() -> list[dict[str, Any]] | dict[str, str]:
    try:
        client = docker.from_env()
        containers = client.containers.list(
            all=True,
            filters={"label": "sputniq.managed=true"},
        )
        return [_managed_container_payload(container) for container in containers]
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/v1/registry/upload-zip")
async def upload_agent_zip(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .zip archive")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        upload_path = tmp_path / file.filename

        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            with zipfile.ZipFile(upload_path, "r") as zip_ref:
                zip_ref.extractall(tmp_path / "extracted")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Invalid zip archive") from exc

        config_path = tmp_path / "extracted" / "config.json"
        if not config_path.exists():
            raise HTTPException(status_code=400, detail="config.json not found in the root of the archive")

        try:
            config = load_config(config_path)
            resolve_references(config)
            detect_cycles(config)

            deployed_services = deploy_app(config, tmp_path / "extracted")

            for workflow in config.workflows:
                _workflows[workflow.id] = workflow

            for tool in config.tools:
                _tools[tool.id] = tool

            return {
                "status": "success",
                "message": (
                    f"Successfully deployed {len(deployed_services)} services from {file.filename}."
                ),
                "registered_workflows": len(config.workflows),
                "registered_tools": len(config.tools),
                "deployed_services": len(deployed_services),
            }
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=f"Configuration error: {exc}") from exc
        except DeploymentError as exc:
            raise HTTPException(status_code=500, detail=f"Deployment failed: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Internal server error: {exc}") from exc


@app.get("/", response_class=HTMLResponse)
async def get_ui() -> HTMLResponse:
    return HTMLResponse(_load_ui_asset("dashboard.html"))


@app.get("/dashboard.js", response_class=PlainTextResponse)
async def get_dashboard_script() -> PlainTextResponse:
    return PlainTextResponse(_load_ui_asset("dashboard.js"), media_type="application/javascript")
