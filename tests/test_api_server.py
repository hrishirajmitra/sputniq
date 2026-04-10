import pytest
from fastapi.testclient import TestClient
import json
import zipfile
import io

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

def _create_zip_file(config_data: dict, filename: str = "config.json") -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr(filename, json.dumps(config_data))
    return zip_buffer.getvalue()

def test_upload_agent_zip_success():
    valid_config = {
        "platform": {
            "name": "test-system",
            "version": "1.0",
            "namespace": "test",
            "runtime": "docker-compose",
            "region": "local"
        },
        "agents": [
            {
                "id": "agent-my",
                "description": "A test agent",
                "entrypoint": "test:test", "model": "gpt-4"
            }
        ],
        "models": [{"id": "gpt-4", "provider": "openai"}], "workflows": [
            {
                "id": "wf-1",
                "entrypoint_step": "step-1",
                "steps": [
                    {"id": "step-1", "type": "agent", "ref": "agent-my"}
                ]
            }
        ]
    }
    zip_bytes = _create_zip_file(valid_config)
    res = client.post(
        "/api/v1/registry/upload-zip",
        files={"file": ("test_app.zip", zip_bytes, "application/zip")}
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "success"
    assert data["registered_workflows"] == 1
    
    # Check if workflow was actually registered
    get_res = client.get("/api/v1/registry/workflows/wf-1")
    assert get_res.status_code == 200

def test_upload_agent_zip_invalid_config():
    # Circular dependency or missing ref
    invalid_config = {
        "platform": {
            "name": "test-system",
            "version": "1.0",
            "namespace": "test",
            "runtime": "docker-compose",
            "region": "local"
        },
        "models": [{"id": "gpt-4", "provider": "openai"}], "workflows": [
            {
                "id": "wf-1",
                "entrypoint_step": "step-1",
                "steps": [
                    {"id": "step-1", "type": "agent", "ref": "missing-agent"}
                ]
            }
        ]
    }
    zip_bytes = _create_zip_file(invalid_config)
    res = client.post(
        "/api/v1/registry/upload-zip",
        files={"file": ("test_app_invalid.zip", zip_bytes, "application/zip")}
    )
    assert res.status_code == 400
    assert "Configuration error" in res.text

def test_upload_agent_zip_no_config():
    zip_bytes = _create_zip_file({}, "not_config.json")
    res = client.post(
        "/api/v1/registry/upload-zip",
        files={"file": ("test_app_no_config.zip", zip_bytes, "application/zip")}
    )
    assert res.status_code == 400
    assert "config.json not found" in res.text

def test_upload_agent_zip_bad_file():
    res = client.post(
        "/api/v1/registry/upload-zip",
        files={"file": ("test_app.txt", b"not-a-zip", "text/plain")}
    )
    assert res.status_code == 400
    assert "must be a .zip archive" in res.text
