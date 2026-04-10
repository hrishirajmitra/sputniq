"""Agent decorator and global registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sputniq.sdk.context import AgentContext

# Global registry: agent_id -> class
_AGENT_REGISTRY: dict[str, type] = {}


def agent(id: str) -> Any:  # noqa: A002
    """Class decorator that registers an agent implementation.

    Usage::

        @agent(id="my-agent")
        class MyAgent:
            async def run(self, ctx: AgentContext) -> str:
                ...
    """
    if not id or not id.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"Invalid agent id: {id!r}")

    def decorator(cls: type) -> type:
        if not hasattr(cls, "run"):
            raise TypeError(f"Agent class '{cls.__name__}' must define an async 'run' method")
        _AGENT_REGISTRY[id] = cls
        cls._agent_id = id  # type: ignore[attr-defined]
        return cls

    return decorator


def get_agent(agent_id: str) -> type:
    """Retrieve a registered agent class by ID."""
    try:
        return _AGENT_REGISTRY[agent_id]
    except KeyError:
        raise KeyError(f"No agent registered with id '{agent_id}'") from None


def registered_agents() -> dict[str, type]:
    """Return a snapshot of the current registry."""
    return dict(_AGENT_REGISTRY)
