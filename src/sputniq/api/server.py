from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sputniq.models.workflows import WorkflowDefinition
from sputniq.models.tools import ToolDefinition

app = FastAPI(title="Sputniq AgentOS Control API", version="0.1.0")

# Local state to mock registry logic
_workflows: dict[str, WorkflowDefinition] = {}
_tools: dict[str, ToolDefinition] = {}

class RegistryResponse(BaseModel):
    status: str
    count: int

@app.post("/api/v1/registry/workflows", response_model=RegistryResponse)
async def register_workflow(workflow: WorkflowDefinition):
    _workflows[workflow.id] = workflow
    return RegistryResponse(status="registered", count=len(_workflows))

@app.get("/api/v1/registry/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(workflow_id: str):
    if workflow_id not in _workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _workflows[workflow_id]

@app.post("/api/v1/registry/tools", response_model=RegistryResponse)
async def register_tool(tool: ToolDefinition):
    _tools[tool.id] = tool
    return RegistryResponse(status="registered", count=len(_tools))

@app.get("/api/v1/registry/tools/{tool_id}", response_model=ToolDefinition)
async def get_tool(tool_id: str):
    if tool_id not in _tools:
        raise HTTPException(status_code=404, detail="Tool not found")
    return _tools[tool_id]
