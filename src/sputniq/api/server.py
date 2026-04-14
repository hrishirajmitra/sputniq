"""Control-plane API for the Sputniq registry and upload flow."""

# ruff: noqa: E501

import shutil
import tempfile
import zipfile
from pathlib import Path

import docker
import httpx
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from sputniq.config.errors import ConfigError
from sputniq.config.parser import detect_cycles, load_config, resolve_references
from sputniq.generator.engine import generate_build_artifacts
from sputniq.models.agents import AgentDefinition
from sputniq.models.models import ModelDefinition
from sputniq.models.orchestrations import OrchestrationDefinition
from sputniq.models.platform import SputniqConfig
from sputniq.models.tools import ToolDefinition
from sputniq.ops.deploy import deploy_app, teardown_app

app = FastAPI(title="Sputniq AgentOS Control API", version="0.1.0")

_agents: dict[str, AgentDefinition] = {}
_tools: dict[str, ToolDefinition] = {}
_models: dict[str, ModelDefinition] = {}
_orchestrations: dict[str, OrchestrationDefinition] = {}
_workflows = _orchestrations


class RegistryResponse(BaseModel):
    status: str
    count: int


@app.post("/api/v1/registry/agents", response_model=RegistryResponse)
async def register_agent(agent: AgentDefinition):
    _agents[agent.id] = agent
    return RegistryResponse(status="registered", count=len(_agents))


@app.get("/api/v1/registry/agents", response_model=list[AgentDefinition])
async def list_agents():
    return list(_agents.values())


@app.get("/api/v1/registry/agents/{agent_id}", response_model=AgentDefinition)
async def get_agent(agent_id: str):
    if agent_id not in _agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agents[agent_id]


@app.post("/api/v1/registry/tools", response_model=RegistryResponse)
async def register_tool(tool: ToolDefinition):
    _tools[tool.id] = tool
    return RegistryResponse(status="registered", count=len(_tools))


@app.get("/api/v1/registry/tools", response_model=list[ToolDefinition])
async def list_tools():
    return list(_tools.values())


@app.get("/api/v1/registry/tools/{tool_id}", response_model=ToolDefinition)
async def get_tool(tool_id: str):
    if tool_id not in _tools:
        raise HTTPException(status_code=404, detail="Tool not found")
    return _tools[tool_id]


@app.post("/api/v1/registry/models", response_model=RegistryResponse)
async def register_model(model: ModelDefinition):
    _models[model.id] = model
    return RegistryResponse(status="registered", count=len(_models))


@app.get("/api/v1/registry/models", response_model=list[ModelDefinition])
async def list_models():
    return list(_models.values())


@app.get("/api/v1/registry/models/{model_id}", response_model=ModelDefinition)
async def get_model(model_id: str):
    if model_id not in _models:
        raise HTTPException(status_code=404, detail="Model not found")
    return _models[model_id]


@app.post("/api/v1/registry/orchestrations", response_model=RegistryResponse)
async def register_orchestration(orchestration: OrchestrationDefinition):
    _orchestrations[orchestration.id] = orchestration
    return RegistryResponse(status="registered", count=len(_orchestrations))


@app.get("/api/v1/registry/orchestrations", response_model=list[OrchestrationDefinition])
async def list_orchestrations():
    return list(_orchestrations.values())


@app.get("/api/v1/registry/orchestrations/{orchestration_id}", response_model=OrchestrationDefinition)
async def get_orchestration(orchestration_id: str):
    if orchestration_id not in _orchestrations:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return _orchestrations[orchestration_id]


@app.post("/api/v1/registry/workflows", response_model=RegistryResponse)
async def register_workflow(workflow: OrchestrationDefinition):
    return await register_orchestration(workflow)


@app.get("/api/v1/registry/workflows", response_model=list[OrchestrationDefinition])
async def list_workflows():
    return await list_orchestrations()


@app.get("/api/v1/registry/workflows/{workflow_id}", response_model=OrchestrationDefinition)
async def get_workflow(workflow_id: str):
    if workflow_id not in _orchestrations:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _orchestrations[workflow_id]


@app.post("/api/v1/proxy")
async def proxy_agent_request(req_data: dict):
    url = req_data.get("url")
    prompt = req_data.get("prompt")
    if not url or not prompt:
        raise HTTPException(status_code=400, detail="url and prompt are required")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"prompt": prompt})
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}") from e


@app.get("/api/v1/registry/deployments")
async def list_deployments():
    """List actively running Sputniq containers."""
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
        deployed = []
        for container in containers:
            if not container.name.startswith("sputniq-"):
                continue

            port = ""
            for env_var in container.attrs["Config"]["Env"]:
                if env_var.startswith("PORT="):
                    port = env_var.split("=")[1]

            deployed.append(
                {
                    "id": container.short_id,
                    "name": container.name,
                    "run_id": container.labels.get("sputniq.run_id", "unknown"),
                    "status": container.status,
                    "image": container.image.tags[0] if container.image.tags else "unknown",
                    "logs_cmd": f"docker logs -f {container.name}",
                    "port": port,
                }
            )
        return deployed
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/v1/registry/deployments/{run_id}")
async def delete_deployment(run_id: str):
    """Tear down and remove all containers for a specific run_id."""
    try:
        removed = teardown_app(run_id)
        if removed == 0:
            raise HTTPException(status_code=404, detail=f"No containers found for run_id {run_id}")
        return {
            "status": "success",
            "message": f"Successfully removed {removed} containers for application run {run_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/v1/logs/{container_id}")
async def get_container_logs(container_id: str):
    """Retrieve tail logs from a container."""
    try:
        client = docker.from_env()
        container = client.containers.get(container_id)
        logs = container.logs(tail=100, stdout=True, stderr=True)
        return {"logs": logs.decode("utf-8")}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found") from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _safe_extract(zip_ref: zipfile.ZipFile, destination: Path) -> None:
    destination_root = destination.resolve()
    for member in zip_ref.infolist():
        member_path = (destination / member.filename).resolve()
        if destination_root not in member_path.parents and member_path != destination_root:
            raise HTTPException(status_code=400, detail="Zip archive contains an unsafe path")
    zip_ref.extractall(destination)


def _entrypoint_path(entrypoint: str) -> Path | None:
    raw_path = entrypoint.split(":", 1)[0]
    if raw_path.endswith((".py", ".js", ".mjs", ".cjs")):
        return Path(raw_path)
    return None


def _validate_entrypoint_files(config: SputniqConfig, app_dir: Path) -> None:
    app_root = app_dir.resolve()
    entrypoints = [(agent.id, agent.entrypoint) for agent in config.agents] + [
        (tool.id, tool.entrypoint) for tool in config.tools
    ]
    for entity_id, entrypoint in entrypoints:
        relative_path = _entrypoint_path(entrypoint)
        if relative_path is None:
            continue

        target = (app_dir / relative_path).resolve()
        if (app_root not in target.parents and target != app_root) or not target.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Entrypoint for '{entity_id}' not found: {relative_path}",
            )


def _register_config(config: SputniqConfig) -> None:
    for agent in config.agents:
        _agents[agent.id] = agent
    for tool in config.tools:
        _tools[tool.id] = tool
    for model in config.models:
        _models[model.id] = model
    for orchestration in config.orchestrations:
        _orchestrations[orchestration.id] = orchestration


@app.post("/api/v1/registry/upload-zip")
async def upload_agent_zip(file: UploadFile = File(...), deploy: bool = Query(default=False)):
    """Validate, register, and optionally deploy an app zip containing config.json."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .zip archive")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        upload_path = tmp_path / file.filename

        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            with zipfile.ZipFile(upload_path, "r") as zip_ref:
                _safe_extract(zip_ref, tmp_path / "extracted")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip archive") from None

        app_dir = tmp_path / "extracted"
        config_path = app_dir / "config.json"
        if not config_path.exists():
            raise HTTPException(status_code=400, detail="config.json not found in the root of the archive")

        try:
            config = load_config(config_path)
            resolve_references(config)
            detect_cycles(config)
            _validate_entrypoint_files(config, app_dir)
            _register_config(config)

            build_dir = app_dir / ".agentos" / "build"
            manifest = generate_build_artifacts(config, build_dir)

            deploy_result = deploy_app(config, app_dir) if deploy else None
            deployed_ports = deploy_result.get("services", {}) if deploy_result else {}
            run_id = deploy_result.get("run_id", "unknown") if deploy_result else "unknown"

            orchestration_url = None
            if deployed_ports:
                first_port = next(iter(deployed_ports.values()))
                orchestration_url = f"http://localhost:{first_port}/"

            return {
                "status": "deployed" if deploy else "registered",
                "message": f"Successfully processed {file.filename}.",
                "run_id": run_id,
                "orchestration_url": orchestration_url,
                "orchestrator_url": orchestration_url,
                "registered_agents": len(config.agents),
                "registered_tools": len(config.tools),
                "registered_models": len(config.models),
                "registered_orchestrations": len(config.orchestrations),
                "registered_workflows": len(config.orchestrations),
                "manifest": manifest,
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=f"Configuration error: {e}") from e
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal server error: {e}") from e


@app.get("/", response_class=HTMLResponse)
async def get_ui():
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sputniq AgentOS</title>
    <style>
        :root {
            color: #1f2933;
            background: #f6f7f9;
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        * { box-sizing: border-box; }
        body { margin: 0; background: #f6f7f9; color: #1f2933; }
        main { max-width: 1120px; margin: 0 auto; padding: 28px 18px 48px; }
        h1 { margin: 0 0 6px; font-size: 34px; font-weight: 800; }
        h2 { margin: 0 0 14px; font-size: 20px; }
        p { margin: 0 0 18px; color: #52616b; line-height: 1.5; }
        section { margin-top: 28px; }
        .upload { display: grid; gap: 10px; max-width: 680px; }
        input[type="file"] { width: 100%; border: 1px solid #b7c4cf; border-radius: 6px; background: #ffffff; padding: 12px; }
        label { color: #334e68; font-size: 14px; }
        button { border: 0; border-radius: 6px; background: #1f7a8c; color: #ffffff; cursor: pointer; font-weight: 700; padding: 11px 16px; }
        button:hover { background: #155e6d; }
        button.secondary { background: #6b7280; }
        button.danger { background: #b42318; }
        button:disabled { cursor: wait; opacity: .68; }
        .message { display: none; border-radius: 6px; padding: 12px; }
        .success { display: block; background: #d9f4e8; color: #0f5132; border: 1px solid #67c391; }
        .error { display: block; background: #fde2df; color: #842029; border: 1px solid #f0a8a0; }
        .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
        .tile { background: #ffffff; border: 1px solid #d8dee4; border-radius: 8px; padding: 16px; min-height: 120px; }
        .tile strong { display: block; color: #102a43; font-size: 28px; }
        table { width: 100%; border-collapse: collapse; background: #ffffff; border: 1px solid #d8dee4; border-radius: 8px; overflow: hidden; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #e4e7eb; vertical-align: top; }
        th { color: #52616b; font-size: 13px; }
        code { white-space: normal; overflow-wrap: anywhere; }
        .actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .modal { display: none; position: fixed; inset: 0; background: rgba(31, 41, 51, .62); padding: 32px 18px; }
        .modal-content { max-width: 900px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 20px; }
        #logOutput { background: #111827; color: #d1fae5; border-radius: 6px; padding: 14px; height: 380px; overflow-y: auto; white-space: pre-wrap; }
        @media (max-width: 760px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } h1 { font-size: 28px; } }
    </style>
</head>
<body>
    <div class="modal" id="logModal">
        <div class="modal-content">
            <div class="actions"><button class="secondary" onclick="closeLogs()">Close</button></div>
            <h2>Container Logs</h2>
            <pre id="logOutput">Fetching logs...</pre>
        </div>
    </div>

    <main>
        <h1>Sputniq AgentOS</h1>
        <p>Agents, tools, models, and orchestrations are registered and managed as first-class platform entities.</p>

        <section>
            <h2>Upload</h2>
            <form id="uploadForm" class="upload">
                <input type="file" id="zipFile" accept=".zip" required>
                <label><input type="checkbox" id="deployToggle"> Run Docker deployment after validation</label>
                <button type="submit">Process Configuration</button>
                <div id="message" class="message"></div>
            </form>
        </section>

        <section class="grid">
            <div class="tile"><strong id="agentCount">0</strong>Agents</div>
            <div class="tile"><strong id="toolCount">0</strong>Tools</div>
            <div class="tile"><strong id="modelCount">0</strong>Models</div>
            <div class="tile"><strong id="orchCount">0</strong>Orchestrations</div>
        </section>

        <section><h2>Orchestrations</h2><table id="orchTable"></table></section>
        <section><h2>Tools</h2><table id="toolTable"></table></section>
        <section><h2>Models</h2><table id="modelTable"></table></section>
        <section><h2>Deployments</h2><table id="depTable"></table></section>
    </main>

    <script>
        function row(values) {
            return '<tr>' + values.map(v => `<td>${v}</td>`).join('') + '</tr>';
        }

        async function fetchData() {
            try {
                const [agentRes, toolRes, modelRes, orchRes, depRes] = await Promise.all([
                    fetch('/api/v1/registry/agents'),
                    fetch('/api/v1/registry/tools'),
                    fetch('/api/v1/registry/models'),
                    fetch('/api/v1/registry/orchestrations'),
                    fetch('/api/v1/registry/deployments')
                ]);
                const agents = await agentRes.json();
                const tools = await toolRes.json();
                const models = await modelRes.json();
                const orchestrations = await orchRes.json();
                const deps = await depRes.json();

                document.getElementById('agentCount').innerText = agents.length;
                document.getElementById('toolCount').innerText = tools.length;
                document.getElementById('modelCount').innerText = models.length;
                document.getElementById('orchCount').innerText = orchestrations.length;

                document.getElementById('orchTable').innerHTML =
                    '<tr><th>ID</th><th>Description</th><th>Entrypoint</th><th>Steps</th></tr>' +
                    orchestrations.map(o => row([o.id, o.description || '-', o.entrypoint_step, o.steps.length])).join('');

                document.getElementById('toolTable').innerHTML =
                    '<tr><th>ID</th><th>Entrypoint</th><th>Timeout</th></tr>' +
                    tools.map(t => row([t.id, `<code>${t.entrypoint}</code>`, `${t.timeout_ms} ms`])).join('');

                document.getElementById('modelTable').innerHTML =
                    '<tr><th>ID</th><th>Provider</th><th>Capabilities</th></tr>' +
                    models.map(m => row([m.id, m.provider, m.capabilities.join(', ')])).join('');

                const depRows = Array.isArray(deps) ? deps.map(d => row([
                    d.name,
                    d.status,
                    `<code>${d.image}</code>`,
                    `<div class="actions"><button class="secondary" onclick="viewLogs('${d.id}')">Logs</button><button class="danger" onclick="deleteApp('${d.run_id}')">Delete</button></div>`
                ])).join('') : row(['-', deps.error || 'Unavailable', '-', '-']);
                document.getElementById('depTable').innerHTML =
                    '<tr><th>Name</th><th>Status</th><th>Image</th><th>Actions</th></tr>' + depRows;
            } catch (e) {
                console.error("Error fetching data", e);
            }
        }

        async function viewLogs(containerId) {
            document.getElementById('logModal').style.display = 'block';
            document.getElementById('logOutput').innerText = 'Fetching logs...';
            try {
                const res = await fetch(`/api/v1/logs/${containerId}`);
                const data = await res.json();
                document.getElementById('logOutput').innerText = res.ok ? data.logs : 'Failed to fetch logs.';
            } catch (e) {
                document.getElementById('logOutput').innerText = 'Error: ' + e;
            }
        }

        function closeLogs() {
            document.getElementById('logModal').style.display = 'none';
        }

        async function deleteApp(runId) {
            if(!confirm("Tear down run " + runId + "?")) return;
            try {
                const res = await fetch(`/api/v1/registry/deployments/${runId}`, { method: 'DELETE' });
                const data = await res.json();
                alert(res.ok ? data.message : "Error: " + (data.detail || "Failed to delete"));
                fetchData();
            } catch (e) {
                alert("Request error: " + e);
            }
        }

        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const file = document.getElementById('zipFile').files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            const btn = e.target.querySelector('button');
            const deploy = document.getElementById('deployToggle').checked;
            btn.innerText = 'Processing...';
            btn.disabled = true;

            const msgBox = document.getElementById('message');
            try {
                const res = await fetch(`/api/v1/registry/upload-zip?deploy=${deploy}`, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                msgBox.className = res.ok ? 'success' : 'error';
                msgBox.innerText = res.ok ? data.message : (data.detail || 'Upload failed');
                if (res.ok) fetchData();
            } catch (err) {
                msgBox.className = 'error';
                msgBox.innerText = err.message;
            } finally {
                btn.innerText = 'Process Configuration';
                btn.disabled = false;
            }
        });

        fetchData();
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)
