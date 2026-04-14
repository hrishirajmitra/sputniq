import httpx
import pytest

from sputniq.api.auth import create_access_token
from sputniq.runtime.gateway import app, coordinators


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
def auth_header():
    token = create_access_token({"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health_check():
    async with _client() as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "version": "0.1.0"}


@pytest.mark.asyncio
async def test_metrics_endpoint():
    async with _client() as client:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "sputniq_build_info" in response.text


@pytest.mark.asyncio
async def test_execute_workflow_unauthorized():
    async with _client() as client:
        response = await client.post("/api/v1/execute", json={"workflow_id": "test-workflow"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_execute_workflow_not_found(auth_header):
    async with _client() as client:
        response = await client.post(
            "/api/v1/execute",
            json={"workflow_id": "missing-workflow", "input_data": {"foo": "bar"}},
            headers=auth_header,
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Workflow not found"


@pytest.mark.asyncio
async def test_execute_workflow_success(auth_header):
    coordinators["test-workflow"] = "mock-coordinator"

    async with _client() as client:
        response = await client.post(
            "/api/v1/execute",
            json={"workflow_id": "test-workflow", "input_data": {"query": "hello"}},
            headers=auth_header,
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "correlation_id" in data
        assert data["status"] == "accepted"

    del coordinators["test-workflow"]
