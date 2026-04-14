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
from sputniq.models.orchestrations import OrchestrationStep
from sputniq.models.platform import SputniqConfig


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
    - Orchestration step refs -> actual entities (agent, tool, model)
    - Orchestration entrypoint -> actual step
    """
    agents = {a.id for a in config.agents}
    tools = {t.id for t in config.tools}
    models = {m.id for m in config.models}

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

    for orchestration in config.orchestrations:
        step_ids = {s.id for s in orchestration.steps}
        ep = orchestration.entrypoint_step
        if ep not in step_ids:
            raise ReferenceError(
                f"Orchestration '{orchestration.id}' entrypoint '{ep}' not found in steps"
            )

        for step in orchestration.steps:
            if step.type == "agent" and step.ref not in agents:
                raise ReferenceError(
                    f"Orchestration '{orchestration.id}' step '{step.id}' "
                    f"references unknown agent '{step.ref}'"
                )
            if step.type == "tool" and step.ref not in tools:
                raise ReferenceError(
                    f"Orchestration '{orchestration.id}' step '{step.id}' "
                    f"references unknown tool '{step.ref}'"
                )
            if step.type == "model" and step.ref not in models:
                raise ReferenceError(
                    f"Orchestration '{orchestration.id}' step '{step.id}' "
                    f"references unknown model '{step.ref}'"
                )
            for subsequent in step.next:
                if subsequent not in step_ids:
                    raise ReferenceError(
                        f"Orchestration '{orchestration.id}' step '{step.id}' "
                        f"references unknown next step '{subsequent}'"
                    )
            for decision, target in step.routes.items():
                if target not in step_ids:
                    raise ReferenceError(
                        f"Orchestration '{orchestration.id}' step '{step.id}' "
                        f"route '{decision}' references unknown step '{target}'"
                    )


def detect_cycles(config: SputniqConfig) -> None:
    """Detect cycles in workflow step graphs using iterative DFS."""

    def _visit(
        step: OrchestrationStep,
        path: set[str],
        visited: set[str],
        steps_map: dict[str, OrchestrationStep],
        orchestration_id: str,
    ) -> None:
        if step.id in path:
            cycle = " -> ".join(sorted(path) + [step.id])
            raise CyclicDependencyError(
                f"Cycle detected in orchestration '{orchestration_id}': {cycle}"
            )
        if step.id in visited:
            return

        path.add(step.id)
        visited.add(step.id)

        for next_id in step.next:
            if (
                step.type == "loop"
                and next_id in path
                and int(step.inputs.get("max_iterations", 0)) > 0
            ):
                continue
            if next_id in steps_map:
                _visit(steps_map[next_id], path, visited, steps_map, orchestration_id)

        path.remove(step.id)

    for orchestration in config.orchestrations:
        steps_map = {s.id: s for s in orchestration.steps}
        visited: set[str] = set()

        for step in orchestration.steps:
            if step.id not in visited:
                _visit(step, set(), visited, steps_map, orchestration.id)
