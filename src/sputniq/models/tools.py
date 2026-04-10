"""Tool entity definition models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSchema(BaseModel):
    """Typed input/output contract for a tool."""

    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class RateLimitConfig(BaseModel):
    """Rate limiting for tool invocations."""

    requests_per_minute: int = Field(default=60, gt=0)


class ToolDefinition(BaseModel):
    """Declarative definition of a callable tool."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    runtime: Literal["python", "node"] = Field(default="python", description="Language runtime environment")
    entrypoint: str = Field(
        ..., min_length=1, description="Module path, e.g. src/tools/search.py:search"
    )
    schema_def: ToolSchema = Field(default_factory=ToolSchema, alias="schema")
    timeout_ms: int = Field(default=10000, gt=0)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    model_config = {"populate_by_name": True}
