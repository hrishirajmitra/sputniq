import pytest
from fastapi.testclient import TestClient

from sputniq.runtime.gateway import app, coordinators
from sputniq.api.auth import create_access_token

client = TestClient(app)

@pytest.fixture
def auth_header():
    token = create_access_token({"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}

def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "sputniq_build_info" in response.text

def test_execute_workflow_unauthorized():
    response = client.post("/api/v1/execute", json={
        "workflow_id": "test-workflow"
    })
    assert response.status_code == 401

def test_execute_workflow_not_found(auth_header):
    response = client.post("/api/v1/execute", json={
        "workflow_id": "missing-workflow",
        "input_data": {"foo": "bar"}
    }, headers=auth_header)
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow not found"

def test_execute_workflow_success(auth_header):
    # Insert a dummy mock for testing
    coordinators["test-workflow"] = "mock-coordinator"
    
    response = client.post("/api/v1/execute", json={
        "workflow_id": "test-workflow",
        "input_data": {"query": "hello"}
    }, headers=auth_header)
    
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "correlation_id" in data
    assert data["status"] == "accepted"
    
    # Cleanup
    del coordinators["test-workflow"]