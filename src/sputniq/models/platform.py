"""Platform-level configuration and top-level config root."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from sputniq.models.agents import AgentDefinition
from sputniq.models.models import ModelDefinition
from sputniq.models.tools import ToolDefinition
from sputniq.models.workflows import WorkflowDefinition


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


# ── Application Server Architecture Definitions ────────────────────────────


class RuntimeDefinition(BaseModel):
    """Defines the runtime environment for the platform.

    Distinguishes between the *System Runtime* (the platform's own
    container/process runtime) and the *App Type Runtime* (the execution
    environment for a specific application artefact type).
    """

    system_runtime: str = Field(
        default="docker",
        description="System-level runtime (docker | kubernetes | process)",
    )
    app_type_runtime: str = Field(
        default="python",
        description="Application artefact runtime (python | node | jvm)",
    )
    runtime_version: str = Field(default="3.11")


class RepositoryConfig(BaseModel):
    """Repository structure definition.

    System Repository — Contains core system components (binaries, INIT configs).
    App Repository    — Contains application definitions, instance configs, load params.
    """

    system_repo: str = Field(
        default=".",
        description="Path or URL to the system repository (binaries, INIT)",
    )
    app_repo: str = Field(
        default=".",
        description="Path or URL to the application repository",
    )


class AppInstanceConfig(BaseModel):
    """Configuration for a specific application instance.

    Includes replica count, load-balancing weight, and optional
    LDAP group binding for external config resolution.
    """

    instance_id: str = Field(default="default-0")
    replicas: int = Field(default=1, ge=1, le=100)
    weight: int = Field(default=1, ge=1, description="Load-balancing weight")
    ldap_group: str | None = Field(
        default=None,
        description="Optional LDAP group for config resolution",
    )
    extra: dict[str, Any] = Field(default_factory=dict)


class SystemINITConfig(BaseModel):
    """System INIT configuration — read by the System Master at boot.

    Defines which core services to start and their parameters.
    """

    kafka_bootstrap_servers: str = Field(default="localhost:9092")
    lb_strategy: str = Field(default="round-robin", description="round-robin | weighted")
    initial_nodes: int = Field(default=1, ge=1, description="Nodes to provision at boot")
    services: list[str] = Field(
        default_factory=lambda: [
            "server-lifecycle-manager",
            "app-lifecycle-manager",
            "security-service",
            "logging-service",
            "deployment-manager",
            "request-dispatcher",
        ],
        description="System services to launch",
    )
    extra: dict[str, Any] = Field(default_factory=dict)


class BootCycleConfig(BaseModel):
    """Boot cycle parameters.

    Separates System Boot Cycle from App Boot Cycle:
      - System Boot: repo check → kafka → provision → system master
      - App Boot: fetch apps → read config → load config → place instances
    """

    auto_bootstrap: bool = Field(
        default=False,
        description="Automatically run full bootstrap on platform start",
    )
    system_init: SystemINITConfig = Field(default_factory=SystemINITConfig)
    app_instances: list[AppInstanceConfig] = Field(default_factory=list)


# ── Root Configuration ──────────────────────────────────────────────────────


class SputniqConfig(BaseModel):
    """Root configuration — mirrors config.json."""

    platform: PlatformConfig
    agents: list[AgentDefinition] = Field(default_factory=list)
    tools: list[ToolDefinition] = Field(default_factory=list)
    models: list[ModelDefinition] = Field(default_factory=list)
    workflows: list[WorkflowDefinition] = Field(default_factory=list)
    infrastructure: InfrastructureConfig = Field(default_factory=InfrastructureConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    runtime: RuntimeDefinition = Field(default_factory=RuntimeDefinition)
    repository: RepositoryConfig = Field(default_factory=RepositoryConfig)
    boot: BootCycleConfig = Field(default_factory=BootCycleConfig)
