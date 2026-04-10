"""Core message types for inter-entity communication."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _nano_ts() -> int:
    return time.time_ns()


def _uuid() -> str:
    return str(uuid4())


class BaseMessage(BaseModel):
    """Fields common to every message on the bus."""

    correlation_id: str = Field(default_factory=_uuid)
    session_id: str = Field(default_factory=_uuid)
    timestamp_ns: int = Field(default_factory=_nano_ts)


# ── Agent messages ──────────────────────────────────────────────────────────


class AgentInput(BaseMessage):
    agent_id: str
    payload: Any


class AgentOutput(BaseMessage):
    agent_id: str
    result: Any


# ── Tool messages ───────────────────────────────────────────────────────────


class ToolRequest(BaseMessage):
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResponse(BaseMessage):
    tool_id: str
    result: Any
    success: bool = True


# ── Model messages ──────────────────────────────────────────────────────────


class ModelRequest(BaseMessage):
    model_id: str
    messages: list[dict[str, str]]
    parameters: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseMessage):
    model_id: str
    content: str
    usage: dict[str, int] = Field(default_factory=dict)


# ── Workflow messages ───────────────────────────────────────────────────────


class WorkflowStepMessage(BaseMessage):
    workflow_id: str
    step_id: str
    payload: Any = None


class WorkflowComplete(BaseMessage):
    workflow_id: str
    result: Any = None
    success: bool = True


# ── System messages ─────────────────────────────────────────────────────────


class Error(BaseMessage):
    error_code: str
    message: str
    entity_id: str
    retryable: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


class HeartBeat(BaseMessage):
    entity_id: str
    status: str = "alive"
