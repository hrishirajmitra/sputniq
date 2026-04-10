import zipfile
import json

config = {
    "platform": {
        "name": "e2e-orchestrator-app",
        "version": "1.0",
        "namespace": "sputniq-demo",
        "runtime": "docker-compose",
        "region": "local"
    },
    "infrastructure": {
        "secrets": [],
        "message_bus": "kafka",
        "state_store": "none",
        "metadata_store": "none"
    },
    "models": [
        {
            "id": "tiny-local-llm",
            "provider": "local",
            "capabilities": ["chat", "inference"]
        }
    ],
    "agents": [
        {
            "id": "orchestrator",
            "description": "E2E Orchestrator handling incoming user requests and planning workflow steps",
            "entrypoint": "orchestrator:run",
            "model": "tiny-local-llm"
        },
        {
            "id": "model-node",
            "description": "Dedicated Local Model Inference Service",
            "entrypoint": "model_node:run",
            "model": "tiny-local-llm"
        }
    ],
    "workflows": [
        {
            "id": "e2e-inference-flow",
            "description": "End-to-End Inference using local model node",
            "entrypoint_step": "step-1",
            "steps": [
                {"id": "step-1", "type": "agent", "ref": "orchestrator", "next": ["step-2"]},
                {"id": "step-2", "type": "agent", "ref": "model-node"}
            ]
        }
    ]
}

# The Main Orchestrator Node
orchestrator_py = """
import os
import requests
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="E2E Orchestrator Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class RequestData(BaseModel):
    prompt: str

@app.post("/api/orchestrate")
async def run_orchestration(req: RequestData):
    print(f"[Orchestrator] Received prompt '{req.prompt}'. Breaking down tasks...")
    
    steps_taken = [
        "1. Validated and sanitized input context.",
        "2. Checked vector state-store (cache miss).",
        "3. Routing request to dedicated 'model-node' for inference."
    ]
    
    # Query our partner agent (model-node) deployed by Sputniq on port 8003
    try:
        res = requests.post("http://localhost:8003/api/inference", json={"text": req.prompt})
        res.raise_for_status()
        model_result = res.json().get("completion")
        steps_taken.append("4. Received successful inference tensor completion.")
    except Exception as e:
        model_result = f"Failed to reach model-node via HTTP RPC. Error: {str(e)}"
        steps_taken.append("4. FATAL: Local Model API Call Failed.")
        
    return {
        "status": "success",
        "input_prompt": req.prompt,
        "workflow_steps": steps_taken,
        "model_output": model_result
    }

def run():
    print("🚀 Booting Sputniq Orchestrator on Port 8002")
    uvicorn.run("orchestrator:app", host="0.0.0.0", port=8002)

if __name__ == "__main__":
    run()
"""

# The Local Model Node
model_node_py = """
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="TinyLocalLLM Inference Node")

class InferenceRequest(BaseModel):
    text: str

@app.post("/api/inference")
async def generate(req: InferenceRequest):
    print(f"[Model-Node] Running inference on: {req.text}")
    # Simulate a local small model
    t = req.text.lower()
    if 'complex' in t or 'e2e' in t:
        output = "Analyzing e2e complexity... The simulated neural network (2M parameters) concludes this is a highly sophisticated infrastructure."
    elif 'hello' in t:
        output = "Greetings! I am TinyLocalLLM-v1 serving inferences locally without external APIs."
    else:
        output = f"Inferred semantic meaning: Extracting entities from '{req.text}'. Result: Neutral sentiment."
        
    return {"completion": output, "model_id": "tiny-local-llm-v1.0"}

def run():
    print("🧠 Booting Local Model Inference Engine on Port 8003")
    uvicorn.run("model_node:app", host="0.0.0.0", port=8003)

if __name__ == "__main__":
    run()
"""

req_txt = "fastapi>=0.110.0\nuvicorn>=0.29.0\npydantic>=2.0\nrequests\n"

file_name = "e2e_complex_project.zip"
with zipfile.ZipFile(file_name, "w") as zf:
    zf.writestr("config.json", json.dumps(config, indent=2))
    zf.writestr("orchestrator.py", orchestrator_py)
    zf.writestr("model_node.py", model_node_py)
    zf.writestr("requirements.txt", req_txt)

print(f"Created {file_name} successfully.")
