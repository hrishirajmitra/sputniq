import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import docker
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from sputniq.config.errors import ConfigError
from sputniq.config.parser import detect_cycles, load_config, resolve_references
from sputniq.models.tools import ToolDefinition
from sputniq.models.workflows import WorkflowDefinition
from sputniq.ops.deploy import DeploymentError, deploy_app
from sputniq.generator.validation import validate_source_tree

app = FastAPI(title="Sputniq AgentOS Control API", version="0.1.0")

_workflows: dict[str, WorkflowDefinition] = {}
_tools: dict[str, ToolDefinition] = {}
_agents: dict[str, dict[str, Any]] = {}
_models: dict[str, dict[str, Any]] = {}
_workflow_apps: dict[str, str] = {}
_tool_apps: dict[str, str] = {}
_model_apps: dict[str, str] = {}
_agent_sessions: dict[str, list[dict[str, Any]]] = {}
_executions: dict[str, dict[str, Any]] = {}
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


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib_request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise HTTPException(status_code=exc.code, detail=detail or url) from exc
    except urllib_error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Service call failed for {url}: {exc.reason}") from exc


def _list_managed_deployments() -> list[dict[str, Any]]:
    client = docker.from_env()
    containers = client.containers.list(
        all=True,
        filters={"label": "sputniq.managed=true"},
    )
    return [_managed_container_payload(container) for container in containers]


def _deployment_for_app(app_name: str, service_role: str) -> dict[str, Any]:
    for deployment in _list_managed_deployments():
        if deployment.get("app_name") == app_name and deployment.get("service_role") == service_role:
            return deployment
    raise HTTPException(status_code=404, detail=f"No '{service_role}' deployment found for app '{app_name}'")


def _managed_container_payload(container: Any) -> dict[str, Any]:
    labels = container.labels
    port = labels.get("sputniq.service_port")

    return {
        "id": container.short_id,
        "name": container.name,
        "service_id": labels.get("sputniq.service_id", container.name.removeprefix("sputniq-")),
        "logical_id": labels.get("sputniq.logical_id", container.name.removeprefix("sputniq-")),
        "service_kind": labels.get("sputniq.service_kind", "unknown"),
        "service_role": labels.get("sputniq.service_role", labels.get("sputniq.service_kind", "unknown")),
        "plane": labels.get("sputniq.plane", "unknown"),
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


@app.get("/api/v1/registry/agents")
async def list_agents() -> list[dict[str, Any]]:
    return list(_agents.values())


@app.get("/api/v1/registry/models")
async def list_models() -> list[dict[str, Any]]:
    return list(_models.values())


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
        return _list_managed_deployments()
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
            validate_source_tree(config, config_path.parent)

            deployed_services = deploy_app(config, tmp_path / "extracted")

            for workflow in config.workflows:
                _workflows[workflow.id] = workflow
                _workflow_apps[workflow.id] = config.platform.name

            for tool in config.tools:
                _tools[tool.id] = tool
                _tool_apps[tool.id] = config.platform.name

            for agent in config.agents:
                _agents[agent.id] = {
                    "id": agent.id,
                    "description": agent.description,
                    "entrypoint": agent.entrypoint,
                    "model": agent.model,
                    "tools": agent.tools,
                    "app_name": config.platform.name,
                }
                _agent_sessions.setdefault(agent.id, [])

            for model in config.models:
                payload = model.model_dump()
                payload["app_name"] = config.platform.name
                _models[model.id] = payload
                _model_apps[model.id] = config.platform.name

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


@app.get("/health")
async def health() -> dict[str, Any]:
    deployments = _list_managed_deployments()
    running = [deployment for deployment in deployments if deployment["status"] == "running"]
    return {
        "status": "ok",
        "version": "0.1.0",
        "registered_workflows": len(_workflows),
        "registered_agents": len(_agents),
        "registered_tools": len(_tools),
        "registered_models": len(_models),
        "managed_services": len(deployments),
        "running_services": len(running),
    }


@app.get("/workflows")
async def management_list_workflows() -> list[dict[str, Any]]:
    return [workflow.model_dump() for workflow in _workflows.values()]


@app.post("/workflows/{workflow_id}/trigger")
async def trigger_workflow(workflow_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    if workflow_id not in _workflow_apps:
        raise HTTPException(status_code=404, detail="Workflow not found")
    gateway = _deployment_for_app(_workflow_apps[workflow_id], "gateway")
    response = _http_json(
        "POST",
        f"http://127.0.0.1:{gateway['port']}/api/v1/execute",
        {
            "workflow_id": workflow_id,
            "input_data": payload,
        },
    )
    execution_id = response.get("execution_id")
    if execution_id:
        _executions[execution_id] = response
        for agent_id, agent in _agents.items():
            if agent["app_name"] == _workflow_apps[workflow_id]:
                _agent_sessions.setdefault(agent_id, []).append(
                    {
                        "session_id": response.get("session_id"),
                        "correlation_id": response.get("correlation_id"),
                        "execution_id": execution_id,
                        "workflow_id": workflow_id,
                    }
                )
    return response


@app.get("/executions/{execution_id}")
async def get_execution(execution_id: str) -> dict[str, Any]:
    if execution_id not in _executions:
        raise HTTPException(status_code=404, detail="Execution not found")
    return _executions[execution_id]


@app.delete("/executions/{execution_id}")
async def cancel_execution(execution_id: str) -> dict[str, Any]:
    if execution_id not in _executions:
        raise HTTPException(status_code=404, detail="Execution not found")
    _executions[execution_id]["status"] = "cancelled"
    return {"status": "cancelled", "execution_id": execution_id}


@app.get("/agents/{agent_id}/sessions")
async def list_agent_sessions(agent_id: str) -> list[dict[str, Any]]:
    if agent_id not in _agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_sessions.get(agent_id, [])


@app.delete("/agents/{agent_id}/sessions/{session_id}")
async def terminate_agent_session(agent_id: str, session_id: str) -> dict[str, Any]:
    if agent_id not in _agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    _agent_sessions[agent_id] = [
        session for session in _agent_sessions.get(agent_id, [])
        if session.get("session_id") != session_id
    ]
    return {"status": "terminated", "agent_id": agent_id, "session_id": session_id}


@app.get("/tools/{tool_id}/invocations")
async def list_tool_invocations(tool_id: str) -> list[dict[str, Any]]:
    if tool_id not in _tool_apps:
        raise HTTPException(status_code=404, detail="Tool not found")
    dispatcher = _deployment_for_app(_tool_apps[tool_id], "tool-dispatcher")
    return _http_json(
        "GET",
        f"http://127.0.0.1:{dispatcher['port']}/api/v1/tools/{tool_id}/invocations",
    )


@app.get("/models/{model_id}/usage")
async def get_model_usage(model_id: str) -> dict[str, Any]:
    if model_id not in _model_apps:
        raise HTTPException(status_code=404, detail="Model not found")
    proxy = _deployment_for_app(_model_apps[model_id], "model-proxy")
    return _http_json(
        "GET",
        f"http://127.0.0.1:{proxy['port']}/api/v1/models/{model_id}/usage",
    )


@app.get("/", response_class=HTMLResponse)
async def get_ui() -> HTMLResponse:
    return HTMLResponse(_load_ui_asset("dashboard.html"))


@app.get("/dashboard.js", response_class=PlainTextResponse)
async def get_dashboard_script() -> PlainTextResponse:
    return PlainTextResponse(_load_ui_asset("dashboard.js"), media_type="application/javascript")
