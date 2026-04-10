"""Workflow definition models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    """A single node in the workflow execution graph."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    type: Literal["agent", "tool", "model", "branch", "parallel"] = "agent"
    ref: str = Field(..., min_length=1, description="Entity ID this step targets")
    next: list[str] = Field(default_factory=list, description="IDs of subsequent steps")
    condition: str | None = Field(default=None, description="Branch condition expression")
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    """Declarative definition of an execution workflow (directed graph)."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str = ""
    entrypoint_step: str = Field(..., min_length=1, description="ID of the first step to execute")
    steps: list[WorkflowStep] = Field(..., min_length=1)
