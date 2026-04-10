import pytest
from fastapi.testclient import TestClient

from sputniq.api.server import app, _workflows, _tools

client = TestClient(app)

@pytest.fixture(autouse=True)
def _clear_registries():
    _workflows.clear()
    _tools.clear()
    yield
    _workflows.clear()
    _tools.clear()

def test_register_and_get_workflow():
    wf_payload = {
        "id": "my-workflow-1",
        "description": "test",
        "entrypoint_step": "step-1",
        "steps": [
            {"id": "step-1", "type": "agent", "ref": "agent-1", "next": []}
        ]
    }
    
    # Register Workflow
    post_res = client.post("/api/v1/registry/workflows", json=wf_payload)
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "registered"
    assert post_res.json()["count"] == 1
    
    # Get Workflow
    get_res = client.get("/api/v1/registry/workflows/my-workflow-1")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == "my-workflow-1"

def test_get_workflow_not_found():
    res = client.get("/api/v1/registry/workflows/non-existent")
    assert res.status_code == 404

def test_register_and_get_tool():
    tool_payload = {
        "id": "my-tool-1",
        "entrypoint": "test_module:test_func",
        "schema": {
            "input": {"type": "object", "properties": {"a": {"type": "string"}}},
            "output": {"type": "string"}
        },
        "timeout_ms": 5000,
        "rate_limit": {"requests_per_minute": 100}
    }
    
    # Register tool
    post_res = client.post("/api/v1/registry/tools", json=tool_payload)
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "registered"
    
    # Get Tool
    get_res = client.get("/api/v1/registry/tools/my-tool-1")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == "my-tool-1"

def test_get_tool_not_found():
    res = client.get("/api/v1/registry/tools/non-existent")
    assert res.status_code == 404
