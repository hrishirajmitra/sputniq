import asyncio
import pytest

from typing import Any
from sputniq.runtime.executors import ToolExecutor, ModelProxy
from sputniq.models.tools import ToolDefinition

@pytest.fixture
def sample_tool_def():
    return ToolDefinition(
        id="echo-tool",
        entrypoint="test:echo"
    )

@pytest.fixture
def test_tool_executor(sample_tool_def):
    executor = ToolExecutor()
    
    async def echo_handler(msg: str):
        return f"Echo: {msg}"
        
    executor.register_tool(sample_tool_def, echo_handler)
    return executor

@pytest.mark.asyncio
async def test_tool_execution(test_tool_executor):
    result = await test_tool_executor.execute("echo-tool", {"msg": "hello"})
    assert result == "Echo: hello"

@pytest.mark.asyncio
async def test_tool_execution_not_found(test_tool_executor):
    with pytest.raises(ValueError, match="not found in registry"):
        await test_tool_executor.execute("missing-tool", {})

@pytest.mark.asyncio
async def test_tool_execution_timeout():
    executor = ToolExecutor()
    slow_def = ToolDefinition(id="slow-tool", entrypoint="test:slow")
    
    async def slow_handler():
        await asyncio.sleep(1)
        return "Done"
        
    executor.register_tool(slow_def, slow_handler)
    
    with pytest.raises(asyncio.TimeoutError):
        # We specify a timeout less than 1.0 second
        await executor.execute("slow-tool", {}, timeout=0.1)

@pytest.mark.asyncio
async def test_model_proxy_success():
    proxy = ModelProxy()
    
    async def mock_openai(model_id: str, msgs: list, **kwargs):
        assert model_id == "gpt-test"
        return "response text"
        
    proxy.register_adapter("openai", mock_openai)
    
    result = await proxy.call("openai", "gpt-test", [{"role": "user", "content": "hi"}])
    assert result == "response text"

@pytest.mark.asyncio
async def test_model_proxy_retry_logic():
    proxy = ModelProxy()
    
    # We will fail 2 times then succeed
    attempts = 0
    
    async def flaky_adapter(model_id: str, msgs: list, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Flaky network")
        return "success finally"
        
    proxy.register_adapter("flaky", flaky_adapter)
    
    # Use max retries = 3
    result = await proxy.call("flaky", "model", [], retries=3)
    assert result == "success finally"
    assert attempts == 3

@pytest.mark.asyncio
async def test_model_proxy_max_retries_exceeded():
    proxy = ModelProxy()
    
    async def failing_adapter(model_id: str, msgs: list, **kwargs):
        raise ValueError("Always fails")
        
    proxy.register_adapter("bad", failing_adapter)
    
    with pytest.raises(RuntimeError, match="All 2 retries failed"):
        await proxy.call("bad", "model", [], retries=2)
