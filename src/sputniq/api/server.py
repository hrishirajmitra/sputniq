import shutil
import tempfile
import zipfile
import json
import docker
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from sputniq.models.workflows import WorkflowDefinition
from sputniq.models.tools import ToolDefinition
from sputniq.config.parser import load_config, resolve_references, detect_cycles
from sputniq.config.errors import ConfigError
from sputniq.ops.deploy import deploy_app, delete_app
from sputniq.state.registry_store import RegistryStore

# ── Application lifecycle ──────────────────────────────────────────────────

registry = RegistryStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to PostgreSQL on startup, disconnect on shutdown."""
    await registry.connect()
    yield
    await registry.disconnect()


app = FastAPI(
    title="Sputniq AgentOS Control API",
    version="0.1.0",
    lifespan=lifespan,
)


# ── App endpoints ──────────────────────────────────────────────────────────


@app.get("/api/v1/apps")
async def list_apps():
    return await registry.list_apps()


@app.delete("/api/v1/apps/{app_id}")
async def delete_application(app_id: str):
    app_data = await registry.get_app(app_id)
    if app_data is None:
        raise HTTPException(status_code=404, detail="App not found")

    if delete_app(app_id, app_data.get("nodes", [])):
        await registry.delete_app(app_id)
        return {"status": "deleted"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete app")


# ── Registry endpoints ─────────────────────────────────────────────────────


class RegistryResponse(BaseModel):
    status: str
    count: int


@app.post("/api/v1/registry/workflows", response_model=RegistryResponse)
async def register_workflow(workflow: WorkflowDefinition):
    await registry.save_workflow(workflow)
    workflows = await registry.list_workflows()
    return RegistryResponse(status="registered", count=len(workflows))


@app.get("/api/v1/registry/workflows", response_model=list[WorkflowDefinition])
async def list_workflows():
    return await registry.list_workflows()


@app.get("/api/v1/registry/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(workflow_id: str):
    wf = await registry.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@app.post("/api/v1/registry/tools", response_model=RegistryResponse)
async def register_tool(tool: ToolDefinition):
    await registry.save_tool(tool)
    tools = await registry.list_tools()
    return RegistryResponse(status="registered", count=len(tools))


@app.get("/api/v1/registry/tools", response_model=list[ToolDefinition])
async def list_tools():
    return await registry.list_tools()


@app.get("/api/v1/registry/tools/{tool_id}", response_model=ToolDefinition)
async def get_tool(tool_id: str):
    tool = await registry.get_tool(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@app.get("/api/v1/registry/deployments")
async def list_deployments():
    """List actively running Sputniq containers."""
    try:
        client = docker.from_env()
        # Find containers created by us (we named them sputniq-*)
        containers = client.containers.list(all=True)
        deployed = []
        for c in containers:
            if c.name.startswith("sputniq-"):
                deployed.append({
                    "id": c.short_id,
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                    "logs_cmd": f"docker logs -f {c.name}"
                })
        return deployed
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/v1/registry/upload-zip")
async def upload_agent_zip(file: UploadFile = File(...)):
    """Uploads a zip archive containing a config.json. Extracts and parses it."""
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .zip archive")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        upload_path = tmp_path / file.filename

        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            with zipfile.ZipFile(upload_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_path / "extracted")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip archive")

        config_path = tmp_path / "extracted" / "config.json"
        if not config_path.exists():
            config_path = tmp_path / "extracted" / "sputniq.json"
            if not config_path.exists():
                raise HTTPException(
                    status_code=400,
                    detail="config.json or sputniq.json not found in the root of the archive",
                )

        try:
            config = load_config(config_path)
            resolve_references(config)
            detect_cycles(config)

            # Persist loaded definitions into PostgreSQL
            if hasattr(config, 'workflows') and config.workflows:
                for wf in config.workflows:
                    await registry.save_workflow(wf)

            if hasattr(config, 'tools') and config.tools:
                for tool in config.tools:
                    await registry.save_tool(tool)

            # Deploy the app (block until finished)
            app_result = deploy_app(config, tmp_path / "extracted")
            if app_result:
                await registry.save_app(app_result["app_id"], app_result)

            return {
                "status": "success",
                "message": f"Successfully parsed and deployed items from {file.filename}.",
                "app_id": app_result["app_id"] if app_result else None,
                "registered_workflows": len(config.workflows) if config.workflows else 0,
                "registered_tools": len(config.tools) if config.tools else 0
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=f"Configuration error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/", response_class=HTMLResponse)
async def get_ui():
    html_content = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sputniq AgentOS</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #0f172a; color: #f8fafc; }
            .container { max-width: 1000px; margin: auto; }
            h1 { color: #38bdf8; border-bottom: 2px solid #1e293b; padding-bottom: 10px; }
            .panel { background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
            input[type="file"] { background: #334155; color: white; padding: 10px; border-radius: 4px; border: 1px solid #475569; width: 100%; box-sizing: border-box; margin-bottom: 10px; }
            button { background: #0ea5e9; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: bold; width: 100%; }
            button:hover { background: #0284c7; }
            button.danger { background: #dc2626; width: auto; padding: 6px 12px;}
            button.danger:hover { background: #b91c1c; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { text-align: left; padding: 12px; border-bottom: 1px solid #334155; }
            th { color: #94a3b8; }
            .badge { background: #059669; padding: 2px 6px; border-radius: 12px; font-size: 12px; }
            #message { margin-top: 10px; padding: 10px; border-radius: 4px; display: none; }
            .success { background: #064e3b; color: #a7f3d0; border: 1px solid #059669; }
            .error { background: #7f1d1d; color: #fecaca; border: 1px solid #dc2626; }
            .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
            .tab { padding: 10px 20px; background: #334155; cursor: pointer; border-radius: 4px; }
            .tab.active { background: #0ea5e9; }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            .node-info { font-size: 0.85em; color: #cbd5e1; display: block; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Sputniq AgentOS Control Plane</h1>
            
            <div class="tabs">
                <div class="tab active" onclick="switchTab('apps')">Applications</div>
                <div class="tab" onclick="switchTab('registry')">Global Registry</div>
            </div>

            <div id="apps" class="tab-content active">
                <div class="panel">
                    <h2>Deploy Application</h2>
                    <form id="uploadForm">
                        <input type="file" id="zipFile" accept=".zip" required>
                        <button type="submit">Upload & Deploy App</button>
                        <div id="message"></div>
                    </form>
                </div>

                <div class="panel">
                    <h2>Running Applications <span class="badge" id="appCount">0</span></h2>
                    <div id="appList"></div>
                </div>
            </div>

            <div id="registry" class="tab-content">
                <div class="panel">
                    <h2>Running Workflows <span class="badge" id="wfCount">0</span></h2>
                    <table id="wfTable"><tr><th>ID</th><th>Description</th><th>Entrypoint Step</th></tr></table>
                </div>
                <div class="panel">
                    <h2>Registered Tools <span class="badge" id="toolCount">0</span></h2>
                    <table id="toolTable"><tr><th>ID</th><th>Entrypoint</th><th>Timeout (ms)</th></tr></table>
                </div>
            </div>
        </div>

        <script>
            function switchTab(tabId) {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                event.target.classList.add('active');
                document.getElementById(tabId).classList.add('active');
            }

            async function deleteApp(appId) {
                if(!confirm('Delete application ' + appId + '?')) return;
                try {
                    await fetch('/api/v1/apps/' + appId, { method: 'DELETE' });
                    fetchData();
                } catch(e) { alert(e); }
            }

            async function fetchData() {
                try {
                    const [wfRes, toolRes, appsRes] = await Promise.all([
                        fetch('/api/v1/registry/workflows'),
                        fetch('/api/v1/registry/tools'),
                        fetch('/api/v1/apps')
                    ]);
                    
                    const workflows = await wfRes.json();
                    document.getElementById('wfCount').innerText = workflows.length;
                    const wfTable = document.getElementById('wfTable');
                    wfTable.innerHTML = '<tr><th>ID</th><th>Description</th><th>Entrypoint Step</th></tr>' + workflows.map(w => `<tr><td>${w.id}</td><td>${w.description}</td><td>${w.entrypoint_step}</td></tr>`).join('');

                    const tools = await toolRes.json();
                    document.getElementById('toolCount').innerText = tools.length;
                    const toolTable = document.getElementById('toolTable');
                    toolTable.innerHTML = '<tr><th>ID</th><th>Entrypoint</th><th>Timeout (ms)</th></tr>' + tools.map(t => `<tr><td>${t.id}</td><td>${t.entrypoint}</td><td>${t.timeout_ms || 'N/A'}</td></tr>`).join('');

                    const apps = await appsRes.json();
                    document.getElementById('appCount').innerText = apps.length;
                    const appList = document.getElementById('appList');
                    
                    if (apps.length === 0) {
                        appList.innerHTML = '<p>No applications deployed.</p>';
                    } else {
                        appList.innerHTML = apps.map(app => `
                            <div style="background: #334155; padding: 15px; margin-bottom: 10px; border-radius: 4px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                    <h3 style="margin: 0; color: #38bdf8;">${app.app_id} (v${app.version || '1.0'})</h3>
                                    <button class="danger" onclick="deleteApp('${app.app_id}')">Delete</button>
                                </div>
                                <table style="font-size: 0.9em; background: #1e293b;">
                                    <tr><th>Service Component</th><th>Target VM (IP)</th><th>Port</th><th>Status</th></tr>
                                    ${(app.nodes || []).map(n => `
                                        <tr>
                                            <td><strong>${n.service_id}</strong><br><span style="color: #94a3b8; font-size: 0.8em">${n.container}</span></td>
                                            <td>${n.hostname}<br><span style="color: #cbd5e1">${n.ip}</span></td>
                                            <td><span style="color: #f59e0b">${n.port || 'N/A'}</span></td>
                                            <td><span class="badge" style="background: ${n.status === 'running' ? '#059669' : '#dc2626'}">${n.status}</span><br><span style="color: #ef4444; font-size: 0.8em">${n.error || ''}</span></td>
                                        </tr>
                                    `).join('')}
                                </table>
                            </div>
                        `).join('');
                    }

                } catch (error) {
                    console.error('Error fetching data:', error);
                }
            }

            document.getElementById('uploadForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const file = document.getElementById('zipFile').files[0];
                const msg = document.getElementById('message');
                msg.style.display = 'block';
                msg.className = '';
                msg.innerText = 'Uploading and deploying... please wait.';

                const formData = new FormData();
                formData.append('file', file);

                try {
                    const res = await fetch('/api/v1/registry/upload-zip', {
                        method: 'POST',
                        body: formData
                    });
                    const result = await res.json();
                    
                    if (res.ok) {
                        msg.className = 'success';
                        msg.innerText = result.message;
                        fetchData();
                    } else {
                        msg.className = 'error';
                        msg.innerText = result.detail || 'Upload failed.';
                    }
                } catch (err) {
                    msg.className = 'error';
                    msg.innerText = err.message;
                }
            });

            fetchData();
            setInterval(fetchData, 10000);
        </script>
    </body>
    </html>"""
    return HTMLResponse(content=html_content)
