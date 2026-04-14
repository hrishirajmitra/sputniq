import io
import json
import zipfile

import httpx
import pytest

from sputniq.api.server import _agents, _models, _tools, _workflows, app


@pytest.fixture(autouse=True)
def _clear_registries():
    _agents.clear()
    _workflows.clear()
    _models.clear()
    _tools.clear()
    yield
    _agents.clear()
    _workflows.clear()
    _models.clear()
    _tools.clear()


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_register_and_get_workflow():
    wf_payload = {
        "id": "my-workflow-1",
        "description": "test",
        "entrypoint_step": "step-1",
        "steps": [{"id": "step-1", "type": "agent", "ref": "agent-1", "next": []}],
    }

    async with _client() as client:
        post_res = await client.post("/api/v1/registry/workflows", json=wf_payload)
        assert post_res.status_code == 200
        assert post_res.json()["status"] == "registered"
        assert post_res.json()["count"] == 1

        get_res = await client.get("/api/v1/registry/workflows/my-workflow-1")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == "my-workflow-1"


@pytest.mark.asyncio
async def test_get_workflow_not_found():
    async with _client() as client:
        res = await client.get("/api/v1/registry/workflows/non-existent")
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_register_and_get_orchestration():
    payload = {
        "id": "main-orchestration",
        "description": "test",
        "entrypoint_step": "step-1",
        "steps": [{"id": "step-1", "type": "agent", "ref": "agent-1", "next": []}],
    }

    async with _client() as client:
        post_res = await client.post("/api/v1/registry/orchestrations", json=payload)
        assert post_res.status_code == 200
        assert post_res.json()["status"] == "registered"

        get_res = await client.get("/api/v1/registry/orchestrations/main-orchestration")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == "main-orchestration"


@pytest.mark.asyncio
async def test_register_agent_and_model():
    agent_payload = {
        "id": "agent-1",
        "entrypoint": "src/agents/agent.py:Agent",
        "model": "gpt-4",
    }
    model_payload = {"id": "gpt-4", "provider": "openai"}

    async with _client() as client:
        model_res = await client.post("/api/v1/registry/models", json=model_payload)
        agent_res = await client.post("/api/v1/registry/agents", json=agent_payload)
        assert model_res.status_code == 200
        assert agent_res.status_code == 200
        assert (await client.get("/api/v1/registry/agents/agent-1")).json()["id"] == "agent-1"
        assert (await client.get("/api/v1/registry/models/gpt-4")).json()["id"] == "gpt-4"


@pytest.mark.asyncio
async def test_register_and_get_tool():
    tool_payload = {
        "id": "my-tool-1",
        "entrypoint": "test_module:test_func",
        "schema": {
            "input": {"type": "object", "properties": {"a": {"type": "string"}}},
            "output": {"type": "string"},
        },
        "timeout_ms": 5000,
        "rate_limit": {"requests_per_minute": 100},
    }

    async with _client() as client:
        post_res = await client.post("/api/v1/registry/tools", json=tool_payload)
        assert post_res.status_code == 200
        assert post_res.json()["status"] == "registered"

        get_res = await client.get("/api/v1/registry/tools/my-tool-1")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == "my-tool-1"


@pytest.mark.asyncio
async def test_get_tool_not_found():
    async with _client() as client:
        res = await client.get("/api/v1/registry/tools/non-existent")
        assert res.status_code == 404


def _create_zip_file(
    config_data: dict,
    filename: str = "config.json",
    files: dict | None = None,
) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr(filename, json.dumps(config_data))
        for path, content in (files or {}).items():
            zip_file.writestr(path, content)
    return zip_buffer.getvalue()


@pytest.mark.asyncio
async def test_upload_agent_zip_success():
    valid_config = {
        "platform": {
            "name": "test-system",
            "version": "1.0",
            "namespace": "test",
            "runtime": "docker-compose",
            "region": "local",
        },
        "agents": [
            {
                "id": "agent-my",
                "description": "A test agent",
                "entrypoint": "src/agents/agent_my.py:AgentMy",
                "model": "gpt-4",
            }
        ],
        "tools": [
            {
                "id": "tool-my",
                "entrypoint": "src/tools/tool_my.py:tool_my",
                "schema": {"input": {}, "output": {}},
            }
        ],
        "models": [{"id": "gpt-4", "provider": "openai"}],
        "orchestrations": [
            {
                "id": "wf-1",
                "entrypoint_step": "step-1",
                "steps": [{"id": "step-1", "type": "agent", "ref": "agent-my"}],
            }
        ],
    }
    zip_bytes = _create_zip_file(
        valid_config,
        files={
            "src/agents/agent_my.py": "class AgentMy:\n    pass\n",
            "src/tools/tool_my.py": "def tool_my():\n    return None\n",
        },
    )

    async with _client() as client:
        res = await client.post(
            "/api/v1/registry/upload-zip",
            files={"file": ("test_app.zip", zip_bytes, "application/zip")},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "registered"
        assert data["registered_agents"] == 1
        assert data["registered_models"] == 1
        assert data["registered_tools"] == 1
        assert data["registered_orchestrations"] == 1
        assert data["registered_workflows"] == 1
        assert data["manifest"]["entities"]["orchestrations"] == ["wf-1"]

        assert (await client.get("/api/v1/registry/workflows/wf-1")).status_code == 200
        assert (await client.get("/api/v1/registry/orchestrations/wf-1")).status_code == 200


@pytest.mark.asyncio
async def test_upload_agent_zip_invalid_config():
    invalid_config = {
        "platform": {
            "name": "test-system",
            "version": "1.0",
            "namespace": "test",
            "runtime": "docker-compose",
            "region": "local",
        },
        "models": [{"id": "gpt-4", "provider": "openai"}],
        "orchestrations": [
            {
                "id": "wf-1",
                "entrypoint_step": "step-1",
                "steps": [{"id": "step-1", "type": "agent", "ref": "missing-agent"}],
            }
        ],
    }
    zip_bytes = _create_zip_file(invalid_config)

    async with _client() as client:
        res = await client.post(
            "/api/v1/registry/upload-zip",
            files={"file": ("test_app_invalid.zip", zip_bytes, "application/zip")},
        )
        assert res.status_code == 400
        assert "Configuration error" in res.text


@pytest.mark.asyncio
async def test_upload_agent_zip_no_config():
    zip_bytes = _create_zip_file({}, "not_config.json")
    async with _client() as client:
        res = await client.post(
            "/api/v1/registry/upload-zip",
            files={"file": ("test_app_no_config.zip", zip_bytes, "application/zip")},
        )
        assert res.status_code == 400
        assert "config.json not found" in res.text


@pytest.mark.asyncio
async def test_upload_agent_zip_bad_file():
    async with _client() as client:
        res = await client.post(
            "/api/v1/registry/upload-zip",
            files={"file": ("test_app.txt", b"not-a-zip", "text/plain")},
        )
        assert res.status_code == 400
        assert "must be a .zip archive" in res.text
