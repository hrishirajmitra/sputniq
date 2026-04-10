import sys
html_code = """
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
        button { background: #0ea5e9; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: bold; width: 100%; margin-bottom: 5px; }
        button:hover { background: #0284c7; }
        button.btn-danger { background: #e11d48; width: auto; font-size: 13px; padding: 6px 12px; }
        button.btn-danger:hover { background: #be123c; }
        button.btn-sec { background: #64748b; width: auto; font-size: 13px; padding: 6px 12px; }
        button.btn-sec:hover { background: #475569; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; }
        .badge { background: #059669; padding: 2px 6px; border-radius: 12px; font-size: 12px; }
        #message { margin-top: 10px; padding: 10px; border-radius: 4px; display: none; }
        .success { background: #064e3b; color: #a7f3d0; border: 1px solid #059669; }
        .error { background: #7f1d1d; color: #fecaca; border: 1px solid #dc2626; }
        
        .run-group { background: #334155; padding: 10px; border-radius: 5px; margin-top: 15px;}
        .run-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid #475569; padding-bottom: 5px; }
        
        #logModal { display: none; position: fixed; z-index: 10; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.7); }
        .modal-content { background-color: #1e293b; margin: 5% auto; padding: 20px; border-radius: 8px; width: 80%; border: 1px solid #475569; }
        #logOutput { background: #0f172a; color: #a5b4fc; padding: 15px; height: 400px; overflow-y: auto; font-family: monospace; white-space: pre-wrap; font-size: 13px; border-radius: 4px; border: 1px solid #334155;}
        .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; line-height: 20px; }
        .close:hover { color: white; }
    </style>
</head>
<body>
    <div id="logModal">
      <div class="modal-content">
        <span class="close" onclick="closeLogs()">&times;</span>
        <h2>Container Logs</h2>
        <div id="logOutput">Fetching logs...</div>
      </div>
    </div>

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
            <h2>Active Deployments <span class="badge" id="depCount">0 containers</span></h2>
            <div id="depsContainer">No active deployments.</div>
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
                    document.getElementById('depCount').innerText = deps.length + " containers";
                    const depsContainer = document.getElementById('depsContainer');
                    
                    if (deps.length === 0) {
                        depsContainer.innerHTML = 'No active deployments.';
                    } else {
                        // Group by run_id
                        const groups = {};
                        deps.forEach(d => {
                            if (!groups[d.run_id]) groups[d.run_id] = [];
                            groups[d.run_id].push(d);
                        });
                        
                        let html = '';
                        for (const [runId, containers] of Object.entries(groups)) {
                            html += `<div class="run-group">`;
                            html += `<div class="run-header">
                                        <h3 style="margin:0;">Run ID: ${runId}</h3>
                                        <button class="btn-danger" onclick="deleteApp('${runId}')">Delete App</button>
                                     </div>`;
                            html += `<table><tr><th>Container Name</th><th>Status</th><th>Image</th><th>Actions</th></tr>`;
                            containers.forEach(d => {
                                let uiBtn = '';
                                if (d.name.includes('research')) {
                                    uiBtn = `<button class="btn-sec" style="background: #10b981;" onclick="window.open('http://localhost:${d.port}', '_blank')">Open UI</button> `;
                                }
                                html += `<tr>
                                    <td><strong>${d.name}</strong></td>
                                    <td><span class="badge" style="background:${d.status === 'running' ? '#059669' : '#b91c1c'}">${d.status}</span></td>
                                    <td><code>${d.image}</code></td>
                                    <td>
                                        ${uiBtn}
                                        <button class="btn-sec" onclick="viewLogs('${d.id}')">Logs</button>
                                    </td>
                                </tr>`;
                            });
                            html += `</table></div>`;
                        }
                        depsContainer.innerHTML = html;
                    }
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

        async function viewLogs(containerId) {
            document.getElementById('logModal').style.display = 'block';
            document.getElementById('logOutput').innerText = 'Fetching logs...';
            try {
                const res = await fetch(`/api/v1/logs/${containerId}`);
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById('logOutput').innerText = data.logs;
                } else {
                    document.getElementById('logOutput').innerText = 'Failed to fetch logs.';
                }
            } catch (e) {
                 document.getElementById('logOutput').innerText = 'Error: ' + e;
            }
        }
        
        function closeLogs() {
            document.getElementById('logModal').style.display = 'none';
        }

        async function deleteApp(runId) {
            if(!confirm("Are you sure you want to completely tear down Run ID: " + runId + "?")) return;
            try {
                const res = await fetch(`/api/v1/registry/deployments/${runId}`, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (res.ok) {
                    alert(data.message);
                } else {
                    alert("Error: " + (data.detail || "Failed to delete"));
                }
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
                    msgBox.innerText = data.message;
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

import re
with open("src/sputniq/api/server.py", "r") as f:
    orig = f.read()

prefix = 'html_content = """'
start_idx = orig.find(prefix) + len(prefix)
end_idx = orig.find('"""', start_idx)

new_content = orig[:start_idx] + "\n" + html_code.strip() + "\n    " + orig[end_idx:]

with open("src/sputniq/api/server.py", "w") as f:
    f.write(new_content)

print("Updated inline HTML.")
