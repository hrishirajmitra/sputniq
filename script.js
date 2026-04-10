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
