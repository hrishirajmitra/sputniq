import logging
from typing import Annotated, Any, Dict, List, Literal, Optional, Sequence, TypedDict

from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import AnyMessage, add_messages
from sputniq.models.workflows import WorkflowDefinition, WorkflowStep

logger = logging.getLogger(__name__)

class WorkflowState(TypedDict):
    """State maintained across the workflow execution."""
    messages: Annotated[list[AnyMessage], add_messages]
    context: dict[str, Any]
    current_step: str
    decision: Optional[str]


class WorkflowCoordinator:
    """Builds and manages LangGraph-based workflows from configuration definitions."""
    
    def __init__(self, definition: WorkflowDefinition, registry: dict = None):
        self.definition = definition
        self.registry = registry or {}
        # Pre-process steps for O(1) lookup
        self._steps: dict[str, WorkflowStep] = {s.id: s for s in definition.steps}
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(WorkflowState)
        
        # Add all nodes dynamically, wrapped in a generic processor
        for step_id, step in self._steps.items():
            builder.add_node(step_id, self._make_node_func(step))
            
        # Add edges
        builder.add_edge(START, self.definition.entrypoint_step)
        
        for step_id, step in self._steps.items():
            if not step.next:
                builder.add_edge(step_id, END)
            elif len(step.next) == 1:
                # If there is just one next step, link directly
                builder.add_edge(step_id, step.next[0])
            else:
                # Branching logic required. We use LangGraph's conditional edges
                # For this simple mock implementation, we route based on the state's `decision` field
                builder.add_conditional_edges(
                    step_id,
                    self._make_router(),
                    {t: t for t in step.next}  # maps decision string to node ID
                )
                
        return builder.compile()

    def _make_node_func(self, step: WorkflowStep):
        """Creates a state-processor function for a specific workflow node."""
        async def node_func(state: WorkflowState) -> dict[str, Any]:
            logger.info(f"Executing step {step.id} of type {step.type}")
            # Mock execution: updates context and optionally makes a routing decision
            new_ctx = state.get("context", {}).copy()
            new_ctx[step.id] = {"executed": True, "ref": step.ref}
            
            # If this is a branching node, we simulate taking the first path for basic ops
            # A real implementation would parse and evaluate step.condition
            decision = step.next[0] if step.next else None
            
            return {
                "context": new_ctx,
                "current_step": step.id,
                "decision": decision
            }
        return node_func

    def _make_router(self):
        """Creates a router function for conditional edges."""
        def router_func(state: WorkflowState) -> str:
            # return the decided node ID
            decision = state.get("decision")
            if not decision:
                logger.warning(f"No decision found for branching from {state.get('current_step')}, failing.")
                # We could route to an error node, but let's assume valid state
                return END
            return decision
        return router_func

    async def execute(self, initial_context: dict[str, Any] = None) -> WorkflowState:
        """Run the compiled LangGraph workflow from start to finish."""
        initial_state = {
            "messages": [],
            "context": initial_context or {},
            "current_step": START,
            "decision": None
        }
        final_state = await self.graph.ainvoke(initial_state)
        return final_state
