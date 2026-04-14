"""Platform-level configuration and top-level config root."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from sputniq.models.agents import AgentDefinition
from sputniq.models.models import ModelDefinition
from sputniq.models.orchestrations import OrchestrationDefinition
from sputniq.models.tools import ToolDefinition


class PlatformConfig(BaseModel):
    """Top-level platform metadata."""

    name: str = Field(..., min_length=1)
    version: str = Field(default="0.1.0")
    namespace: str = Field(default="default")
    runtime: Literal["kubernetes", "docker-compose"] = "docker-compose"
    region: str = Field(default="local")


class InfrastructureConfig(BaseModel):
    """Infrastructure requirements."""

    secrets: list[str] = Field(default_factory=list)
    message_bus: Literal["kafka", "nats"] = "kafka"
    state_store: Literal["redis", "dynamodb"] = "redis"
    metadata_store: Literal["postgresql"] = "postgresql"
    extra: dict[str, Any] = Field(default_factory=dict)


class ObservabilityConfig(BaseModel):
    """Observability stack settings."""

    tracing: bool = True
    metrics: bool = True
    logging: bool = True
    trace_endpoint: str = "http://localhost:14268"
    metrics_endpoint: str = "http://localhost:9090"
    log_endpoint: str = "http://localhost:3100"


class SputniqConfig(BaseModel):
    """Root configuration — mirrors config.json."""

    platform: PlatformConfig
    agents: list[AgentDefinition] = Field(default_factory=list)
    tools: list[ToolDefinition] = Field(default_factory=list)
    models: list[ModelDefinition] = Field(default_factory=list)
    orchestrations: list[OrchestrationDefinition] = Field(default_factory=list)
    workflows: list[OrchestrationDefinition] = Field(
        default_factory=list,
        description="Deprecated alias for orchestrations.",
    )
    infrastructure: InfrastructureConfig = Field(default_factory=InfrastructureConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @model_validator(mode="after")
    def _sync_orchestration_aliases(self) -> SputniqConfig:
        if self.orchestrations and self.workflows:
            by_id = {orchestration.id: orchestration for orchestration in self.orchestrations}
            for workflow in self.workflows:
                if workflow.id in by_id and workflow != by_id[workflow.id]:
                    raise ValueError(
                        f"Conflicting orchestration/workflow definitions for '{workflow.id}'"
                    )
                by_id.setdefault(workflow.id, workflow)
            merged = list(by_id.values())
            self.orchestrations = merged
            self.workflows = merged
        elif self.workflows:
            self.orchestrations = list(self.workflows)
        else:
            self.workflows = list(self.orchestrations)
        return self
