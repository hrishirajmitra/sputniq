"""Tests for the Sputniq Gateway with mocked RegistryStore."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from sputniq.api.auth import create_access_token
from sputniq.models.workflows import WorkflowDefinition, WorkflowStep


def _wf(wf_id: str = "test-workflow") -> WorkflowDefinition:
    return WorkflowDefinition(
        id=wf_id,
        description="test",
        entrypoint_step="step-1",
        steps=[WorkflowStep(id="step-1", type="agent", ref="agent-1")],
    )


@pytest.fixture(autouse=True)
def mock_gateway_registry():
    """Patch the gateway's RegistryStore and coordinator cache."""
    wf_store: dict[str, WorkflowDefinition] = {}

    mock = MagicMock()
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()

    async def _get_wf(wf_id):
        return wf_store.get(wf_id)

    mock.get_workflow = AsyncMock(side_effect=_get_wf)
    mock._wf_store = wf_store  # expose for test mutation

    with patch("sputniq.runtime.gateway.registry", mock), \
         patch("sputniq.runtime.gateway._coordinator_cache", {}):
        yield mock


@pytest.fixture
def client():
    from sputniq.runtime.gateway import app
    return TestClient(app)


@pytest.fixture
def auth_header():
    token = create_access_token({"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "sputniq_build_info" in response.text


def test_execute_workflow_unauthorized(client):
    response = client.post("/api/v1/execute", json={
        "workflow_id": "test-workflow"
    })
    assert response.status_code == 401


def test_execute_workflow_not_found(client, auth_header):
    response = client.post("/api/v1/execute", json={
        "workflow_id": "missing-workflow",
        "input_data": {"foo": "bar"}
    }, headers=auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow not found"


def test_execute_workflow_success(client, auth_header, mock_gateway_registry):
    # Insert a workflow definition into the mock store
    mock_gateway_registry._wf_store["test-workflow"] = _wf("test-workflow")

    response = client.post("/api/v1/execute", json={
        "workflow_id": "test-workflow",
        "input_data": {"query": "hello"}
    }, headers=auth_header)

    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "correlation_id" in data
    assert data["status"] == "accepted"