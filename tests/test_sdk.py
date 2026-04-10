"""Tests for the Python SDK - Agent context and decorators."""

import pytest
from unittest.mock import AsyncMock

from sputniq.sdk.context import AgentContext
from sputniq.sdk.decorators import agent, get_agent, registered_agents, _AGENT_REGISTRY

@pytest.fixture(autouse=True)
def _clear_registry():
    """Clear the agent registry before each test to ensure isolation."""
    _AGENT_REGISTRY.clear()
    yield
    _AGENT_REGISTRY.clear()

def test_agent_decorator_registers_class():
    """Test that the @agent decorator registers a class with an async run method."""
    @agent(id="my-test-agent")
    class MyTestAgent:
        async def run(self, ctx: AgentContext) -> str:
            return "success"
            
    assert "my-test-agent" in registered_agents()
    registered_class = get_agent("my-test-agent")
    assert registered_class is MyTestAgent
    assert registered_class._agent_id == "my-test-agent"

def test_agent_decorator_rejects_invalid_id():
    """Test that the decorator raises ValueError for invalid IDs."""
    with pytest.raises(ValueError, match="Invalid agent id"):
        @agent(id="")
        class EmptyIdAgent:
            async def run(self, ctx: AgentContext) -> str:
                pass

    with pytest.raises(ValueError, match="Invalid agent id"):
        @agent(id="invalid id!")
        class InvalidIdAgent:
            async def run(self, ctx: AgentContext) -> str:
                pass

def test_agent_decorator_requires_run_method():
    """Test that the decorator raises TypeError if no run method is defined."""
    with pytest.raises(TypeError, match="must define an async 'run' method"):
        @agent(id="no-run-method")
        class NoRunMethodAgent:
            pass

def test_get_agent_raises_key_error():
    """Test that get_agent raises KeyError for unregistered agents."""
    with pytest.raises(KeyError, match="No agent registered"):
        get_agent("unregistered-agent")

@pytest.mark.asyncio
async def test_agent_context_initialization():
    """Test basic initialization of AgentContext."""
    ctx = AgentContext(
        agent_id="test-agent",
        session_id="session-123",
        correlation_id="corr-456",
        input={"query": "hello"}
    )
    
    assert ctx.agent_id == "test-agent"
    assert ctx.session_id == "session-123"
    assert ctx.correlation_id == "corr-456"
    assert ctx.input == {"query": "hello"}
    assert ctx.memory == []
    assert ctx.events == []

@pytest.mark.asyncio
async def test_agent_context_tool_call():
    """Test that context.tool() calls the injected handler."""
    mock_handler = AsyncMock(return_value="tool_result")
    
    ctx = AgentContext(
        agent_id="test",
        session_id="session",
        correlation_id="corr",
        input="test",
        tool_handler=mock_handler
    )
    
    result = await ctx.tool("my_tool", arg1="value1")
    
    assert result == "tool_result"
    mock_handler.assert_called_once_with("my_tool", arg1="value1")

@pytest.mark.asyncio
async def test_agent_context_model_call():
    """Test that context.model() calls the injected handler."""
    mock_handler = AsyncMock(return_value="model_result")
    
    ctx = AgentContext(
        agent_id="test",
        session_id="session",
        correlation_id="corr",
        input="test",
        model_handler=mock_handler
    )
    
    messages = [{"role": "user", "content": "hello"}]
    result = await ctx.model("my_model", messages, temp=0.5)
    
    assert result == "model_result"
    mock_handler.assert_called_once_with("my_model", messages, temp=0.5)

@pytest.mark.asyncio
async def test_agent_context_unimplemented_handlers():
    """Test that unconfigured handlers raise NotImplementedError."""
    ctx = AgentContext(
        agent_id="test",
        session_id="session",
        correlation_id="corr",
        input="test"
    )
    
    with pytest.raises(NotImplementedError, match="No tool handler configured"):
        await ctx.tool("any_tool")
        
    with pytest.raises(NotImplementedError, match="No model handler configured"):
        await ctx.model("any_model", [])

def test_agent_context_emit_events():
    """Test the emit functionality for recording events."""
    ctx = AgentContext(
        agent_id="test",
        session_id="session",
        correlation_id="corr",
        input="test"
    )
    
    ctx.emit("test_event", {"some": "data"})
    ctx.emit("another_event")
    
    events = ctx.events
    assert len(events) == 2
    assert events[0] == {"type": "test_event", "payload": {"some": "data"}}
    assert events[1] == {"type": "another_event", "payload": None}

@pytest.mark.asyncio
async def test_agent_context_for_testing():
    """Test the for_testing factory method creates a ready-to-test context."""
    ctx = AgentContext.for_testing(
        agent_id="mock-agent",
        input="mock-input",
        tool_return="mocked-tool",
        model_return="mocked-model"
    )
    
    assert ctx.agent_id == "mock-agent"
    assert ctx.input == "mock-input"
    
    tool_res = await ctx.tool("some_tool")
    assert tool_res == "mocked-tool"
    ctx.tool_mock.assert_called_once_with("some_tool")
    
    model_res = await ctx.model("some_model", [])
    assert model_res == "mocked-model"
    ctx.model_mock.assert_called_once_with("some_model", [])
