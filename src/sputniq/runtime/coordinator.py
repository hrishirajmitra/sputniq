import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages

from sputniq.models.orchestrations import OrchestrationDefinition, OrchestrationStep

logger = logging.getLogger(__name__)


def _merge_context(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


def _latest(_left: Any, right: Any) -> Any:
    return right


class OrchestrationState(TypedDict):
    """State maintained across orchestration execution."""

    messages: Annotated[list[AnyMessage], add_messages]
    context: Annotated[dict[str, Any], _merge_context]
    outputs: Annotated[dict[str, Any], _merge_context]
    current_step: Annotated[str, _latest]
    decision: Annotated[str | None, _latest]


class OrchestrationCoordinator:
    """Build and execute a LangGraph orchestration from configuration."""

    def __init__(self, definition: OrchestrationDefinition, registry: dict | None = None):
        self.definition = definition
        self.registry = registry or {}
        self._steps: dict[str, OrchestrationStep] = {step.id: step for step in definition.steps}
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(OrchestrationState)

        for step_id, step in self._steps.items():
            builder.add_node(step_id, self._make_node_func(step))

        builder.add_edge(START, self.definition.entrypoint_step)

        for step_id, step in self._steps.items():
            if not step.next:
                builder.add_edge(step_id, END)
            elif len(step.next) == 1:
                builder.add_edge(step_id, step.next[0])
            elif step.type == "parallel":
                for next_step in step.next:
                    builder.add_edge(step_id, next_step)
            else:
                builder.add_edge(step_id, step.next[0])

        return builder.compile()

    def _make_node_func(self, step: OrchestrationStep):
        async def node_func(state: OrchestrationState) -> dict[str, Any]:
            logger.info("Executing orchestration step %s of type %s", step.id, step.type)
            new_ctx = state.get("context", {}).copy()
            output = await self._execute_step(step, state)
            new_ctx[step.id] = {
                "executed": True,
                "type": step.type,
                "ref": step.ref,
                "output": output,
            }
            decision = self._resolve_decision(step, state, new_ctx)

            return {
                "context": new_ctx,
                "outputs": {step.id: output},
                "current_step": step.id,
                "decision": decision,
            }

        return node_func

    async def _execute_step(self, step: OrchestrationStep, state: OrchestrationState) -> Any:
        if step.type in {"branch", "loop", "parallel", "join", "end"}:
            return {"control": step.type, "inputs": step.inputs}

        handler = self._handler_for(step)
        if handler is None:
            return {
                "status": "recorded",
                "reason": "no runtime handler registered",
                "inputs": step.inputs,
            }

        kwargs = {"step": step, "state": state, "inputs": step.inputs}
        result = self._call_handler(handler, kwargs)
        if inspect.isawaitable(result):
            return await result
        return await asyncio.to_thread(lambda: result)

    def _handler_for(self, step: OrchestrationStep) -> Callable[..., Any] | None:
        if not step.ref:
            return None

        typed_registry = self.registry.get(f"{step.type}s")
        if isinstance(typed_registry, dict) and step.ref in typed_registry:
            return typed_registry[step.ref]

        handler = self.registry.get(step.ref)
        return handler if callable(handler) else None

    def _call_handler(self, handler: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
        signature = inspect.signature(handler)
        has_kwargs = any(
            param.kind is inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
        if has_kwargs:
            return handler(**kwargs)

        accepted = {key: value for key, value in kwargs.items() if key in signature.parameters}
        if accepted:
            return handler(**accepted)
        return handler(kwargs["inputs"])

    def _resolve_decision(
        self,
        step: OrchestrationStep,
        state: OrchestrationState,
        context: dict[str, Any],
    ) -> str | None:
        if not step.next:
            return None
        if step.type == "parallel":
            return None

        requested_route = step.inputs.get("route")
        if requested_route in step.next:
            return requested_route
        if requested_route in step.routes:
            return step.routes[requested_route]

        if step.condition and step.condition in context:
            context_value = str(context[step.condition]).lower()
            if context_value in step.routes:
                return step.routes[context_value]

        if step.type == "loop":
            loop_counts = dict(context.get("_loop_counts", {}))
            count = int(loop_counts.get(step.id, 0)) + 1
            loop_counts[step.id] = count
            context["_loop_counts"] = loop_counts
            max_iterations = int(step.inputs.get("max_iterations", self.definition.max_iterations))
            if count < max_iterations and step.condition and context.get(step.condition):
                return step.next[0]
            return step.next[-1]

        if len(step.next) > 1:
            logger.info("Step %s did not set a branch decision; using the first route", step.id)
        return step.next[0]

    async def execute(self, initial_context: dict[str, Any] | None = None) -> OrchestrationState:
        state: OrchestrationState = {
            "messages": [],
            "context": initial_context or {},
            "outputs": {},
            "current_step": START,
            "decision": None,
        }
        pending = [self.definition.entrypoint_step]
        iterations = 0

        while pending:
            iterations += 1
            if iterations > self.definition.max_iterations * max(len(self._steps), 1):
                raise RuntimeError(
                    f"Orchestration '{self.definition.id}' exceeded its iteration guard"
                )

            step_id = pending.pop(0)
            step = self._steps[step_id]
            output = await self._execute_step(step, state)
            new_context = dict(state["context"])
            new_context[step.id] = {
                "executed": True,
                "type": step.type,
                "ref": step.ref,
                "output": output,
            }
            decision = self._resolve_decision(step, state, new_context)
            state = {
                "messages": state["messages"],
                "context": new_context,
                "outputs": {**state["outputs"], step.id: output},
                "current_step": step.id,
                "decision": decision,
            }

            if not step.next:
                continue
            if step.type == "parallel":
                pending = step.next + pending
            elif len(step.next) == 1:
                pending.insert(0, step.next[0])
            elif decision in step.next:
                pending.insert(0, decision)
            else:
                pending.insert(0, step.next[0])

        return state


WorkflowState = OrchestrationState
WorkflowCoordinator = OrchestrationCoordinator
