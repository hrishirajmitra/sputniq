"""Tests for the Sputniq API server with mocked RegistryStore."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
import json
import zipfile
import io

from sputniq.models.workflows import WorkflowDefinition, WorkflowStep
from sputniq.models.tools import ToolDefinition


# ── Helpers ─────────────────────────────────────────────────────────────────


def _wf(wf_id: str = "my-workflow-1") -> WorkflowDefinition:
    return WorkflowDefinition(
        id=wf_id,
        description="test",
        entrypoint_step="step-1",
        steps=[WorkflowStep(id="step-1", type="agent", ref="agent-1")],
    )


def _tool(tool_id: str = "my-tool-1") -> ToolDefinition:
    return ToolDefinition(
        id=tool_id,
        entrypoint="test_module:test_func",
        schema={"input": {"type": "object"}, "output": {"type": "string"}},
        timeout_ms=5000,
        rate_limit={"requests_per_minute": 100},
    )


# ── Mock registry setup ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_registry():
    """Patch the RegistryStore used by the API server with async mocks.

    We maintain an in-memory dict behind the mock so tests exercise
    the full register → list → get flow realistically.
    """
    wf_store: dict[str, WorkflowDefinition] = {}
    tool_store: dict[str, ToolDefinition] = {}
    app_store: dict[str, dict] = {}

    mock = MagicMock()
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()

    # Workflows
    async def _save_wf(wf):
        wf_store[wf.id] = wf

    async def _get_wf(wf_id):
        return wf_store.get(wf_id)

    async def _list_wf():
        return list(wf_store.values())

    async def _delete_wf(wf_id):
        return wf_store.pop(wf_id, None) is not None

    mock.save_workflow = AsyncMock(side_effect=_save_wf)
    mock.get_workflow = AsyncMock(side_effect=_get_wf)
    mock.list_workflows = AsyncMock(side_effect=_list_wf)
    mock.delete_workflow = AsyncMock(side_effect=_delete_wf)

    # Tools
    async def _save_tool(t):
        tool_store[t.id] = t

    async def _get_tool(tid):
        return tool_store.get(tid)

    async def _list_tools():
        return list(tool_store.values())

    async def _delete_tool(tid):
        return tool_store.pop(tid, None) is not None

    mock.save_tool = AsyncMock(side_effect=_save_tool)
    mock.get_tool = AsyncMock(side_effect=_get_tool)
    mock.list_tools = AsyncMock(side_effect=_list_tools)
    mock.delete_tool = AsyncMock(side_effect=_delete_tool)

    # Apps
    async def _save_app(aid, data):
        app_store[aid] = data

    async def _get_app(aid):
        return app_store.get(aid)

    async def _list_apps():
        return list(app_store.values())

    async def _delete_app(aid):
        return app_store.pop(aid, None) is not None

    mock.save_app = AsyncMock(side_effect=_save_app)
    mock.get_app = AsyncMock(side_effect=_get_app)
    mock.list_apps = AsyncMock(side_effect=_list_apps)
    mock.delete_app = AsyncMock(side_effect=_delete_app)

    with patch("sputniq.api.server.registry", mock):
        yield mock


@pytest.fixture
def client():
    from sputniq.api.server import app
    return TestClient(app, raise_server_exceptions=True)


# ── Workflow endpoint tests ─────────────────────────────────────────────────


def test_register_and_get_workflow(client):
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


def test_get_workflow_not_found(client):
    res = client.get("/api/v1/registry/workflows/non-existent")
    assert res.status_code == 404


def test_register_and_get_tool(client):
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


def test_get_tool_not_found(client):
    res = client.get("/api/v1/registry/tools/non-existent")
    assert res.status_code == 404


def test_list_workflows_empty(client):
    res = client.get("/api/v1/registry/workflows")
    assert res.status_code == 200
    assert res.json() == []


def test_list_tools_empty(client):
    res = client.get("/api/v1/registry/tools")
    assert res.status_code == 200
    assert res.json() == []


def test_list_apps_empty(client):
    res = client.get("/api/v1/apps")
    assert res.status_code == 200
    assert res.json() == []


# ── Zip upload tests ────────────────────────────────────────────────────────


def _create_zip_file(config_data: dict, filename: str = "config.json") -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr(filename, json.dumps(config_data))
    return zip_buffer.getvalue()


def test_upload_agent_zip_success(client):
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

    with patch("sputniq.api.server.deploy_app") as mock_deploy:
        mock_deploy.return_value = {"app_id": "test-system", "version": "1.0", "nodes": []}
        res = client.post(
            "/api/v1/registry/upload-zip",
            files={"file": ("test_app.zip", zip_bytes, "application/zip")}
        )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "success"
    assert data["registered_workflows"] == 1

    # Check if workflow was actually registered in mock store
    get_res = client.get("/api/v1/registry/workflows/wf-1")
    assert get_res.status_code == 200


def test_upload_agent_zip_invalid_config(client):
    # Missing ref
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


def test_upload_agent_zip_no_config(client):
    zip_bytes = _create_zip_file({}, "not_config.json")
    res = client.post(
        "/api/v1/registry/upload-zip",
        files={"file": ("test_app_no_config.zip", zip_bytes, "application/zip")}
    )
    assert res.status_code == 400
    assert "not found in the root of the archive" in res.text


def test_upload_agent_zip_bad_file(client):
    res = client.post(
        "/api/v1/registry/upload-zip",
        files={"file": ("test_app.txt", b"not-a-zip", "text/plain")}
    )
    assert res.status_code == 400
    assert "must be a .zip archive" in res.text
