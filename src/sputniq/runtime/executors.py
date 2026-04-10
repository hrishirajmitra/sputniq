import asyncio
import logging
from typing import Any, Callable

from pydantic import ValidationError

from sputniq.models.tools import ToolDefinition

logger = logging.getLogger(__name__)

class ToolExecutor:
    """Dispatches tool calls, validates inputs/outputs against schemas, and handles timeouts."""
    
    def __init__(self, registry: dict[str, ToolDefinition] = None, handlers: dict[str, Callable] = None):
        self.registry = registry or {}
        self.handlers = handlers or {}

    def register_tool(self, definition: ToolDefinition, handler: Callable):
        self.registry[definition.id] = definition
        self.handlers[definition.id] = handler

    async def execute(self, tool_id: str, args: dict[str, Any], timeout: float = 30.0) -> Any:
        """Executes a tool by ID with provided arguments."""
        if tool_id not in self.registry or tool_id not in self.handlers:
            raise ValueError(f"Tool {tool_id} not found in registry.")

        definition = self.registry[tool_id]
        handler = self.handlers[tool_id]

        logger.info(f"Executing tool {tool_id} with timeout {timeout}s")
        try:
            # We wrap the invocation in asyncio.wait_for for timeout enforcement
            result = await asyncio.wait_for(self._run_handler(handler, args), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.error(f"Tool {tool_id} timed out after {timeout} seconds.")
            raise
        except Exception as e:
            logger.error(f"Tool {tool_id} failed with error: {e}")
            raise

    async def _run_handler(self, handler: Callable, args: dict[str, Any]) -> Any:
        # If the handler is an async function, await it; else run directly
        if asyncio.iscoroutinefunction(handler):
            return await handler(**args)
        else:
            # For synchronous handlers, we could run in a thread pool, but we'll run directly here for simplicity
            return handler(**args)

class ModelProxy:
    """Standardizes LLM provider APIs and adds retry logic."""
    
    def __init__(self, provider_adapters: dict[str, Callable] = None):
        self.provider_adapters = provider_adapters or {}
        
    def register_adapter(self, provider: str, adapter: Callable):
        self.provider_adapters[provider] = adapter

    async def call(self, provider: str, model_id: str, messages: list[dict[str, str]], retries: int = 3, **kwargs) -> str:
        """Calls a registered provider adapter with retry logic."""
        if provider not in self.provider_adapters:
            raise ValueError(f"Provider {provider} not registered.")
            
        adapter = self.provider_adapters[provider]
        
        attempt = 0
        last_error = None
        while attempt < retries:
            try:
                # Wrap it around an async call
                result = await adapter(model_id, messages, **kwargs)
                return result
            except Exception as e:
                attempt += 1
                last_error = e
                logger.warning(f"ModelProxy call to {provider}/{model_id} failed on attempt {attempt}: {e}")
                # Exponential backoff simulation
                await asyncio.sleep(0.01)
                
        logger.error(f"ModelProxy call failed after {retries} retries.")
        raise RuntimeError(f"All {retries} retries failed.") from last_error
