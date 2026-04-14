"""Model (LLM) entity definition."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelDefinition(BaseModel):
    """Declarative definition of an inference endpoint."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9][a-z0-9\-\.]*$")
    provider: Literal["openai", "anthropic", "bedrock", "vllm", "google", "custom"] = "openai"
    capabilities: list[str] = Field(
        default_factory=lambda: ["chat"],
        description="e.g. chat, function-calling, embeddings",
    )
    endpoint: str | None = Field(default=None, description="Custom endpoint URL for vllm/custom")
    config: dict[str, Any] = Field(default_factory=dict, description="Provider-specific settings")
