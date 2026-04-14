"""Backward-compatible aliases for orchestration definition models."""

from __future__ import annotations

from sputniq.models.orchestrations import OrchestrationDefinition, OrchestrationStep

WorkflowStep = OrchestrationStep
WorkflowDefinition = OrchestrationDefinition

__all__ = ["WorkflowDefinition", "WorkflowStep"]
