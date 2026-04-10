import shutil
import tempfile
import zipfile
import json
import docker
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import httpx

from sputniq.models.workflows import WorkflowDefinition
from sputniq.models.tools import ToolDefinition
from sputniq.config.parser import load_config, resolve_references, detect_cycles
from sputniq.config.errors import ConfigError
from sputniq.ops.deploy import deploy_app

app = FastAPI(title="Sputniq AgentOS Control API", version="0.1.0")

# Local state to mock registry logic
_workflows: dict[str, WorkflowDefinition] = {}
_tools: dict[str, ToolDefinition] = {}

class RegistryResponse(BaseModel):
    status: str
    count: int

@app.post("/api/v1/registry/workflows", response_model=RegistryResponse)
async def register_workflow(workflow: WorkflowDefinition):
    _workflows[workflow.id] = workflow
    return RegistryResponse(status="registered", count=len(_workflows))

@app.get("/api/v1/registry/workflows", response_model=list[WorkflowDefinition])
async def list_workflows():
    return list(_workflows.values())

@app.get("/api/v1/registry/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(workflow_id: str):
    if workflow_id not in _workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _workflows[workflow_id]

@app.post("/api/v1/registry/tools", response_model=RegistryResponse)
async def register_tool(tool: ToolDefinition):
    _tools[tool.id] = tool
    return RegistryResponse(status="registered", count=len(_tools))

@app.post("/api/v1/proxy")
async def proxy_agent_request(req_data: dict):
    url = req_data.get("url")
    prompt = req_data.get("prompt")
    if not url or not prompt:
        raise HTTPException(status_code=400, detail="url and prompt are required")
        
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"prompt": prompt})
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")

@app.get("/api/v1/registry/tools", response_model=list[ToolDefinition])
async def list_tools():
    return list(_tools.values())

@app.get("/api/v1/registry/tools/{tool_id}", response_model=ToolDefinition)
async def get_tool(tool_id: str):
    if tool_id not in _tools:
        raise HTTPException(status_code=404, detail="Tool not found")
    return _tools[tool_id]

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
                port = ""
                env_vars = c.attrs['Config']['Env']
                for e in env_vars:
                    if e.startswith('PORT='):
                        port = e.split('=')[1]
                        
                deployed.append({
                    "id": c.short_id,
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                    "logs_cmd": f"docker logs -f {c.name}",
                    "port": port
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
            raise HTTPException(status_code=400, detail="config.json not found in the root of the archive")
            
        try:
            config = load_config(config_path)
            resolve_references(config)
            detect_cycles(config)
            
            # Register loaded definitions into the in-memory dictionary
            if hasattr(config, 'workflows') and config.workflows:
                for wf in config.workflows:
                    _workflows[wf.id] = wf
                    
            if hasattr(config, 'tools') and config.tools:
                for tool in config.tools:
                    _tools[tool.id] = tool
            
            # Deploy the app (block until finished)
            deployed_ports = deploy_app(config, tmp_path / "extracted")
                    
            orchestrator_url = None
            if deployed_ports:
                # Find the main agent URL if available
                for svc, port in deployed_ports.items():
                    if 'orchestrator' in svc or 'research' in svc:
                        orchestrator_url = f"http://localhost:{port}/"
                        break
                
                # Fallback to the first available service port if nothing specialized fits
                if not orchestrator_url:
                    first_port = next(iter(deployed_ports.values()))
                    orchestrator_url = f"http://localhost:{first_port}/"
                    
            return {
                "status": "success", 
                "message": f"Successfully parsed and deployed items from {file.filename}.",
                "orchestrator_url": orchestrator_url,
                "registered_workflows": len(config.workflows) if config.workflows else 0,
                "registered_tools": len(config.tools) if config.tools else 0
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=f"Configuration error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #0f172a; color: #f8fafc; }
            .container { max-width: 1000px; margin: auto; }
            h1 { color: #38bdf8; border-bottom: 2px solid #1e293b; padding-bottom: 10px; }
            .panel { background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
            input[type="file"] { background: #334155; color: white; padding: 10px; border-radius: 4px; border: 1px solid #475569; width: 100%; box-sizing: border-box; margin-bottom: 10px; }
            button { background: #0ea5e9; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: bold; width: 100%; }
            button:hover { background: #0284c7; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { text-align: left; padding: 12px; border-bottom: 1px solid #334155; }
            th { color: #94a3b8; }
            .badge { background: #059669; padding: 2px 6px; border-radius: 12px; font-size: 12px; }
            #message { margin-top: 10px; padding: 10px; border-radius: 4px; display: none; }
            .success { background: #064e3b; color: #a7f3d0; border: 1px solid #059669; }
            .error { background: #7f1d1d; color: #fecaca; border: 1px solid #dc2626; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Sputniq AgentOS Control Plane</h1>
            
            <div class="panel">
                <h2>Deploy Application</h2>
                <form id="uploadForm">
                    <input type="file" id="zipFile" accept=".zip" required>
                    <button type="submit">Upload & Deploy Configuration</button>
                    <div id="message"></div>
                </form>
            </div>

            <div class="panel">
                <h2>Active Deployments (Containers) <span class="badge" id="depCount">0</span></h2>
                <table id="depTable">
                    <tr><th>Container Name</th><th>Status</th><th>Image</th><th>Actions</th><th>Logs</th></tr>
                </table>
            </div>

            <div class="panel">
                <h2>Running Workflows <span class="badge" id="wfCount">0</span></h2>
                <table id="wfTable">
                    <tr><th>ID</th><th>Description</th><th>Entrypoint Step</th></tr>
                </table>
            </div>

            <div class="panel">
                <h2>Registered Tools <span class="badge" id="toolCount">0</span></h2>
                <table id="toolTable">
                    <tr><th>ID</th><th>Entrypoint</th><th>Timeout (ms)</th></tr>
                </table>
            </div>
        </div>

        <script>
            async function fetchData() {
                try {
                    const [wfRes, toolRes, depRes] = await Promise.all([
                        fetch('/api/v1/registry/workflows'),
                        fetch('/api/v1/registry/tools'),
                        fetch('/api/v1/registry/deployments')
                    ]);
                    const workflows = await wfRes.json();
                    const tools = await toolRes.json();
                    const deps = await depRes.json();
                    
                    if (Array.isArray(deps)) {
                        document.getElementById('depCount').innerText = deps.length;
                        const depTable = document.getElementById('depTable');
                        
                        let rows = '<tr><th>Container Name</th><th>Status</th><th>Image</th><th>Actions</th><th>Logs</th></tr>';
                        deps.forEach(d => {
                            let actionBtn = '';
                            if (d.port) {
                                if (d.name.includes('smart-assistant')) {
                                    actionBtn = `<a href="http://localhost:${d.port}/" target="_blank" style="background: #10b981; padding: 5px 10px; font-size: 11px; color: white; text-decoration: none; border-radius: 4px;">Open UI</a>`;
                                } else if (d.name.includes('orchestrator')) {
                                    actionBtn = `<a href="http://localhost:${d.port}/" target="_blank" style="background: #8b5cf6; padding: 5px 10px; font-size: 11px; color: white; text-decoration: none; border-radius: 4px;">Open UI</a>`;
                                } else if (d.name.includes('research-agent')) {
                                    actionBtn = `<a href="http://localhost:${d.port}/" target="_blank" style="background: #f59e0b; padding: 5px 10px; font-size: 11px; color: white; text-decoration: none; border-radius: 4px;">Open UI (Port ${d.port})</a>`;
                                } else {
                                    actionBtn = `<a href="http://localhost:${d.port}/" target="_blank" style="background: #3b82f6; padding: 5px 10px; font-size: 11px; color: white; text-decoration: none; border-radius: 4px;">Open UI (Port ${d.port})</a>`;
                                }
                            }
                            rows += `<tr><td><strong>${d.name}</strong></td><td><span class="badge" style="background:${d.status === 'running' ? '#059669' : '#b91c1c'}">${d.status}</span></td><td><code>${d.image.split(':')[0]}</code></td><td>${actionBtn}</td><td><code>sudo ${d.logs_cmd}</code></td></tr>`;
                        });
                        depTable.innerHTML = rows;
                    }

                    document.getElementById('wfCount').innerText = workflows.length;
                    const wfTable = document.getElementById('wfTable');
                    wfTable.innerHTML = '<tr><th>ID</th><th>Description</th><th>Entrypoint Step</th></tr>' + 
                        workflows.map(w => `<tr><td>${w.id}</td><td>${w.description || '-'}</td><td>${w.entrypoint_step}</td></tr>`).join('');

                    document.getElementById('toolCount').innerText = tools.length;
                    const toolTable = document.getElementById('toolTable');
                    toolTable.innerHTML = '<tr><th>ID</th><th>Entrypoint</th><th>Timeout (ms)</th></tr>' + 
                        tools.map(t => `<tr><td>${t.id}</td><td>${t.entrypoint}</td><td>${t.timeout_ms || 1000}</td></tr>`).join('');
                } catch (e) {
                    console.error("Error fetching data", e);
                }
            }

            async function interact(url, agentName) {
                const userPrompt = prompt(`Ask the ${agentName} a question (e.g. 'execute a complex task flow'):`);
                if (!userPrompt) return;
                
                try {
                    const res = await fetch('/api/v1/proxy', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ url: url, prompt: userPrompt })
                    });
                    const data = await res.json();
                    alert(`🤖 ${agentName} Reply:\\n\\n` + JSON.stringify(data, null, 2));
                } catch (e) {
                    alert(`Could not reach ${agentName}. Make sure the container is actually running! Error: ` + e);
                }
            }

            document.getElementById('uploadForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const file = document.getElementById('zipFile').files[0];
                if (!file) return;

                const formData = new FormData();
                formData.append('file', file);
                
                const btn = e.target.querySelector('button');
                btn.innerText = 'Deploying...';
                btn.disabled = true;
                
                const msgBox = document.getElementById('message');
                
                try {
                    const res = await fetch('/api/v1/registry/upload-zip', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    
                    msgBox.style.display = 'block';
                    if (res.ok) {
                        msgBox.className = 'success';
                        let extraMsg = data.orchestrator_url ? `<br><br><a href="${data.orchestrator_url}" target="_blank" style="background: #10b981; padding: 10px 15px; font-size: 14px; color: white; display: inline-block; text-decoration: none; border-radius: 4px;">🚀 Open Dedicated UI</a>` : '';
                        msgBox.innerHTML = `<strong>${data.message}</strong>` + extraMsg;
                        fetchData(); // Refresh UI
                    } else {
                        msgBox.className = 'error';
                        msgBox.innerText = data.detail || 'Upload failed';
                    }
                } catch (err) {
                    msgBox.style.display = 'block';
                    msgBox.className = 'error';
                    msgBox.innerText = err.message;
                } finally {
                    btn.innerText = 'Upload & Deploy Configuration';
                    btn.disabled = false;
                }
            });

            // Initial load
            fetchData();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

