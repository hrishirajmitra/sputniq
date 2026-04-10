import pytest
from fastapi.testclient import TestClient

from sputniq.runtime.gateway import app, coordinators

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}

def test_execute_workflow_not_found():
    response = client.post("/api/v1/execute", json={
        "workflow_id": "missing-workflow",
        "input_data": {"foo": "bar"}
    })
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow not found"

def test_execute_workflow_success():
    # Insert a dummy mock for testing
    coordinators["test-workflow"] = "mock-coordinator"
    
    response = client.post("/api/v1/execute", json={
        "workflow_id": "test-workflow",
        "input_data": {"query": "hello"}
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "correlation_id" in data
    assert data["status"] == "accepted"
    
    # Cleanup
    del coordinators["test-workflow"]