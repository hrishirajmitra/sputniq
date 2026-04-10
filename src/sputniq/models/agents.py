"""Agent entity definition models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MemoryConfig(BaseModel):
    """Agent memory configuration."""

    type: Literal["sliding-window", "summary", "full"] = "sliding-window"
    max_tokens: int = Field(default=4096, gt=0)


class RetryConfig(BaseModel):
    """Retry behaviour for agent operations."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff: Literal["exponential", "linear", "fixed"] = "exponential"


class AgentDefinition(BaseModel):
    """Declarative definition of an autonomous agent."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str = ""
    runtime: Literal["python", "node"] = Field(default="python", description="Language runtime environment")
    entrypoint: str = Field(
        ..., min_length=1, description="Module path, e.g. src/agents/research.py:ResearchAgent"
    )
    model: str = Field(..., min_length=1, description="ID of the model this agent uses")
    tools: list[str] = Field(default_factory=list, description="Tool IDs this agent may invoke")
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    system_prompt: str = ""
    max_turns: int = Field(default=10, ge=1)
    timeout_ms: int = Field(default=30000, gt=0)
    retry: RetryConfig = Field(default_factory=RetryConfig)
