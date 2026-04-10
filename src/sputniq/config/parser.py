"""Configuration parsing and validation."""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sputniq.config.errors import (
    ConfigLoadError,
    CyclicDependencyError,
    ReferenceError,
)
from sputniq.config.errors import (
    ValidationError as ConfigValidationError,
)
from sputniq.models.platform import SputniqConfig
from sputniq.models.workflows import WorkflowStep


def load_config(path: Path | str) -> SputniqConfig:
    """Load and validate the platform configuration from a JSON file."""
    p = Path(path)
    if not p.exists():
        raise ConfigLoadError(f"Configuration file not found: {p}")

    try:
        content = p.read_text("utf-8")
        data: dict[str, Any] = json.loads(content)
        return SputniqConfig.model_validate(data)
    except json.JSONDecodeError as e:
        raise ConfigLoadError(f"Failed to parse JSON: {e}") from e
    except ValidationError as e:
        raise ConfigValidationError(f"Configuration validation failed: {e}") from e


def resolve_references(config: SputniqConfig) -> None:
    """Validate that all references across entities resolve correctly.

    Checks:
    - Agent tool refs -> actual tools
    - Agent model refs -> actual models
    - Workflow step refs -> actual entities (agent, tool, model)
    - Workflow entrypoint -> actual step
    """
    agents = {a.id for a in config.agents}
    tools = {t.id for t in config.tools}
    models = {m.id for m in config.models}
    all_entities = agents | tools | models

    for agent in config.agents:
        if agent.model not in models:
            raise ReferenceError(
                f"Agent '{agent.id}' references unknown model '{agent.model}'"
            )
        for tool in agent.tools:
            if tool not in tools:
                raise ReferenceError(
                    f"Agent '{agent.id}' references unknown tool '{tool}'"
                )

    for workflow in config.workflows:
        step_ids = {s.id for s in workflow.steps}
        ep = workflow.entrypoint_step
        if ep not in step_ids:
            raise ReferenceError(
                f"Workflow '{workflow.id}' entrypoint '{ep}' not found in steps"
            )

        for step in workflow.steps:
            if step.ref not in all_entities:
                raise ReferenceError(
                    f"Workflow '{workflow.id}' step '{step.id}' "
                    f"references unknown entity '{step.ref}'"
                )
            for subsequent in step.next:
                if subsequent not in step_ids:
                    raise ReferenceError(
                        f"Workflow '{workflow.id}' step '{step.id}' "
                        f"references unknown next step '{subsequent}'"
                    )


def detect_cycles(config: SputniqConfig) -> None:
    """Detect cycles in workflow step graphs using iterative DFS."""

    def _visit(
        step: WorkflowStep,
        path: set[str],
        visited: set[str],
        steps_map: dict[str, WorkflowStep],
        workflow_id: str,
    ) -> None:
        if step.id in path:
            cycle = " -> ".join(sorted(path) + [step.id])
            raise CyclicDependencyError(
                f"Cycle detected in workflow '{workflow_id}': {cycle}"
            )
        if step.id in visited:
            return

        path.add(step.id)
        visited.add(step.id)

        for next_id in step.next:
            if next_id in steps_map:
                _visit(steps_map[next_id], path, visited, steps_map, workflow_id)

        path.remove(step.id)

    for workflow in config.workflows:
        steps_map = {s.id: s for s in workflow.steps}
        visited: set[str] = set()

        for step in workflow.steps:
            if step.id not in visited:
                _visit(step, set(), visited, steps_map, workflow.id)
