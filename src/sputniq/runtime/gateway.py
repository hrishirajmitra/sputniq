import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from sputniq.runtime.coordinator import WorkflowCoordinator
from sputniq.api.auth import verify_token, TokenData
from sputniq.observability.metrics import get_metrics_payload
from sputniq.state.registry_store import RegistryStore

# Persistent registry for workflow definition lookup
registry = RegistryStore()

# In-memory cache of compiled coordinators (hydrated on-demand from DB)
_coordinator_cache: dict[str, WorkflowCoordinator] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to PostgreSQL on startup, disconnect on shutdown."""
    await registry.connect()
    yield
    await registry.disconnect()


app = FastAPI(title="Sputniq AgentOS Gateway", version="0.1.0", lifespan=lifespan)

class WorkflowExecutionRequest(BaseModel):
    workflow_id: str
    input_data: dict = Field(default_factory=dict)

class WorkflowExecutionResponse(BaseModel):
    session_id: str
    correlation_id: str
    status: str


class GatewayService:
    @staticmethod
    @app.post("/api/v1/execute", response_model=WorkflowExecutionResponse)
    async def execute_workflow(req: WorkflowExecutionRequest, current_user: TokenData = Depends(verify_token)):
        # Check cache first, then fall back to persistent registry
        if req.workflow_id not in _coordinator_cache:
            wf_def = await registry.get_workflow(req.workflow_id)
            if wf_def is None:
                raise HTTPException(status_code=404, detail="Workflow not found")
            # Hydrate the coordinator from the persisted definition
            _coordinator_cache[req.workflow_id] = WorkflowCoordinator(wf_def)

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
