import uuid
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from sputniq.runtime.coordinator import WorkflowCoordinator
from sputniq.api.auth import verify_token, TokenData
from sputniq.observability.metrics import get_metrics_payload

app = FastAPI(title="Sputniq AgentOS Gateway", version="0.1.0")

class WorkflowExecutionRequest(BaseModel):
    workflow_id: str
    input_data: dict = Field(default_factory=dict)

class WorkflowExecutionResponse(BaseModel):
    session_id: str
    correlation_id: str
    status: str

# A mock registry to hold our compiled coordinators
# In a real system, this would be backed by a database and loaded during startup
coordinators: dict[str, WorkflowCoordinator] = {}

class GatewayService:
    @staticmethod
    @app.post("/api/v1/execute", response_model=WorkflowExecutionResponse)
    async def execute_workflow(req: WorkflowExecutionRequest, current_user: TokenData = Depends(verify_token)):
        if req.workflow_id not in coordinators:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        session_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        # Start execution in the background or submit to a task queue (e.g. celery / ARQ / our Kafka Bus)
        # For phase 2.5, we just simulate ingestion:
        
        return WorkflowExecutionResponse(
            session_id=session_id,
            correlation_id=correlation_id,
            status="accepted"
        )
        
    @staticmethod
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "0.1.0"}

    @staticmethod
    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics():
        return get_metrics_payload().decode("utf-8")
