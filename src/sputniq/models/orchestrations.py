"""Orchestration entity definition models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

GraphStepType = Literal["agent", "tool", "model", "branch", "loop", "parallel", "join", "end"]


class OrchestrationStep(BaseModel):
    """A single node in a LangGraph-backed orchestration graph."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    type: GraphStepType = "agent"
    ref: str | None = Field(
        default=None,
        description=(
            "Entity ID for agent/tool/model nodes. Control-flow nodes do not require a ref."
        ),
    )
    next: list[str] = Field(default_factory=list, description="IDs of subsequent steps")
    condition: str | None = Field(
        default=None,
        description="Context key or expression used by branch/loop control nodes.",
    )
    routes: dict[str, str] = Field(
        default_factory=dict,
        description="Decision value to step ID mapping for conditional control flow.",
    )
    inputs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_ref_for_step_type(self) -> OrchestrationStep:
        if self.type in {"agent", "tool", "model"} and not self.ref:
            raise ValueError(f"{self.type} step '{self.id}' requires ref")
        if self.routes:
            unknown_routes = set(self.routes.values()) - set(self.next)
            if unknown_routes:
                raise ValueError(
                    f"Step '{self.id}' routes to targets not present in next: "
                    f"{', '.join(sorted(unknown_routes))}"
                )
        return self


class OrchestrationDefinition(BaseModel):
    """Declarative directed execution graph over agents, tools, models, and control nodes."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str = ""
    entrypoint_step: str = Field(..., min_length=1, description="ID of the first step to execute")
    steps: list[OrchestrationStep] = Field(..., min_length=1)
    max_iterations: int = Field(
        default=25,
        ge=1,
        description="Upper bound used by runtime loop guards.",
    )
    state_schema: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_step_identity(self) -> OrchestrationDefinition:
        step_ids = [step.id for step in self.steps]
        duplicate_ids = sorted({step_id for step_id in step_ids if step_ids.count(step_id) > 1})
        if duplicate_ids:
            raise ValueError(
                f"Orchestration '{self.id}' contains duplicate step IDs: "
                f"{', '.join(duplicate_ids)}"
            )
        if self.entrypoint_step not in set(step_ids):
            raise ValueError(
                f"Orchestration '{self.id}' entrypoint '{self.entrypoint_step}' "
                "not found in steps"
            )
        return self
