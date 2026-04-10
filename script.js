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
                            if (d.name === 'sputniq-smart-assistant') {
                                actionBtn = `<button style="background: #10b981; padding: 5px 10px; font-size: 11px; width: auto;" onclick="interact()">Test API</button>`;
                            }
                            rows += `<tr><td><strong>${d.name}</strong></td><td><span class="badge" style="background:${d.status === 'running' ? '#059669' : '#b91c1c'}">${d.status}</span></td><td><code>${d.image}</code></td><td>${actionBtn}</td><td><code>sudo ${d.logs_cmd}</code></td></tr>`;
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

            async function interact() {
                const prompt = prompt("Ask the Smart Assistant a question (e.g. 'calculate pi' or 'hello'):");
                if (!prompt) return;
                
                try {
                    const res = await fetch('http://localhost:8001/api/ask', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ prompt: prompt })
                    });
                    const data = await res.json();
                    alert("🤖 Smart Assistant Reply:

" + data.reply);
                } catch (e) {
                    alert("Could not reach the assistant. Make sure the container is actually running! Error: " + e);
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
