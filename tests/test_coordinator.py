import pytest

from sputniq.models.workflows import WorkflowDefinition, WorkflowStep
from sputniq.runtime.coordinator import WorkflowCoordinator


@pytest.fixture
def sample_workflow_def() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="test-workflow",
        description="A test workflow",
        entrypoint_step="step-1",
        steps=[
            WorkflowStep(
                id="step-1",
                type="agent",
                ref="test-agent",
                next=["step-2"]
            ),
            WorkflowStep(
                id="step-2",
                type="tool",
                ref="test-tool",
                next=[]
            )
        ]
    )

@pytest.fixture
def branching_workflow_def() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="branch-workflow",
        description="A test branching workflow",
        entrypoint_step="start-step",
        steps=[
            WorkflowStep(
                id="start-step",
                type="agent",
                ref="router-agent",
                next=["path-a", "path-b"]
            ),
            WorkflowStep(
                id="path-a",
                type="model",
                ref="model-a",
                next=[]
            ),
            WorkflowStep(
                id="path-b",
                type="model",
                ref="model-b",
                next=[]
            )
        ]
    )

def test_coordinator_initialization(sample_workflow_def):
    """Test that a basic workflow compiles successfully into a state graph."""
    coordinator = WorkflowCoordinator(sample_workflow_def)
    assert coordinator.definition == sample_workflow_def
    assert isinstance(coordinator._steps, dict)
    assert len(coordinator._steps) == 2

@pytest.mark.asyncio
async def test_workflow_linear_execution(sample_workflow_def):
    """Test linear execution of steps using a invoke."""
    coordinator = WorkflowCoordinator(sample_workflow_def)

    # We execute without errors
    final_state = await coordinator.execute(initial_context={"foo": "bar"})

    # Did it collect changes in the context correctly?
    assert "context" in final_state

    # Step 1 was executed
    assert "step-1" in final_state["context"], "Step 1 context key missing"
    assert final_state["context"]["step-1"]["executed"] is True
    assert final_state["context"]["step-1"]["ref"] == "test-agent"

    # Step 2 was executed
    assert "step-2" in final_state["context"], "Step 2 context key missing"
    assert final_state["context"]["step-2"]["executed"] is True
    assert final_state["context"]["step-2"]["ref"] == "test-tool"

    # The original context remains
    assert final_state["context"]["foo"] == "bar"

    # Check end step
    assert final_state["current_step"] == "step-2"

@pytest.mark.asyncio
async def test_workflow_branching_execution(branching_workflow_def):
    """Test standard branch routing execution logic."""
    coordinator = WorkflowCoordinator(branching_workflow_def)
    final_state = await coordinator.execute()

    assert "context" in final_state

    # The start step executed
    assert "start-step" in final_state["context"]

    # Since our mock router always chooses the first path right now
    assert "path-a" in final_state["context"]
    assert "path-b" not in final_state["context"]

    # Ensure graph traversed up to the final target
    assert final_state["current_step"] == "path-a"

@pytest.mark.asyncio
async def test_orchestration_dispatches_registered_handler(sample_workflow_def):
    async def agent_handler(inputs):
        return {"answer": inputs.get("question", "ok")}

    sample_workflow_def.steps[0].inputs["question"] = "done"
    coordinator = WorkflowCoordinator(
        sample_workflow_def,
        registry={"agents": {"test-agent": agent_handler}},
    )
    final_state = await coordinator.execute()

    assert final_state["outputs"]["step-1"] == {"answer": "done"}
    assert final_state["context"]["step-1"]["output"] == {"answer": "done"}
