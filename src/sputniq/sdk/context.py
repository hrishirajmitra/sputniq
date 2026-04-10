"""AgentContext — the runtime interface injected into every agent.run() call."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock


class AgentContext:
    """Provides an agent with access to tools, models, memory, and telemetry.

    In production the tool/model callables are wired to the ToolDispatcher
    and ModelProxy respectively. In tests they can be injected as mocks.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        session_id: str,
        correlation_id: str,
        input: Any,  # noqa: A002
        tool_handler: Any | None = None,
        model_handler: Any | None = None,
        memory: list[dict[str, Any]] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.session_id = session_id
        self.correlation_id = correlation_id
        self.input = input
        self.memory: list[dict[str, Any]] = memory or []
        self._tool_handler = tool_handler or self._unimplemented_tool
        self._model_handler = model_handler or self._unimplemented_model
        self._events: list[dict[str, Any]] = []
        self.logger = logging.getLogger(f"sputniq.agent.{agent_id}")

    # ── Public SDK surface ────────────────────────────────────────────────

    async def tool(self, tool_id: str, **kwargs: Any) -> Any:
        """Invoke a registered tool by ID with keyword arguments."""
        return await self._tool_handler(tool_id, **kwargs)

    async def model(self, model_id: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Call an LLM endpoint and return the text response."""
        return await self._model_handler(model_id, messages, **kwargs)

    def emit(self, event_type: str, payload: Any = None) -> None:
        """Emit a structured event (recorded for testing / observability)."""
        self._events.append({"type": event_type, "payload": payload})

    @property
    def events(self) -> list[dict[str, Any]]:
        """Return emitted events (read-only view)."""
        return list(self._events)

    # ── Stub handlers used when no real runtime is wired ──────────────────

    @staticmethod
    async def _unimplemented_tool(tool_id: str, **_: Any) -> None:
        raise NotImplementedError(
            f"No tool handler configured; cannot call tool '{tool_id}'"
        )

    @staticmethod
    async def _unimplemented_model(model_id: str, _messages: Any, **_: Any) -> None:
        raise NotImplementedError(
            f"No model handler configured; cannot call model '{model_id}'"
        )

    # ── Factory helpers ───────────────────────────────────────────────────

    @classmethod
    def for_testing(
        cls,
        *,
        agent_id: str = "test-agent",
        session_id: str = "test-session",
        correlation_id: str = "test-correlation",
        input: Any = None,  # noqa: A002
        tool_return: Any = None,
        model_return: str = "mock-response",
    ) -> "AgentContext":
        """Convenience factory for unit tests — returns an AgentContext with
        pre-configured async mocks for tool and model handlers."""
        tool_mock = AsyncMock(return_value=tool_return)
        model_mock = AsyncMock(return_value=model_return)
        ctx = cls(
            agent_id=agent_id,
            session_id=session_id,
            correlation_id=correlation_id,
            input=input,
            tool_handler=tool_mock,
            model_handler=model_mock,
        )
        # Expose mocks for assertion in tests
        ctx.tool_mock = tool_mock  # type: ignore[attr-defined]
        ctx.model_mock = model_mock  # type: ignore[attr-defined]
        return ctx
