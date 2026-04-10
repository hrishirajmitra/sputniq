from abc import ABC, abstractmethod
from typing import AsyncIterator, Any
import json
from pydantic import BaseModel

class MessageProducer(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Initialize connection to the message bus."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Close connection to the message bus."""
        ...

    @abstractmethod
    async def publish(self, topic: str, message: dict[str, Any] | BaseModel) -> None:
        """Publish a message to a topic."""
        ...

class MessageConsumer(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Initialize connection to the message bus."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Close connection to the message bus."""
        ...

    @abstractmethod
    async def consume(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Consume messages, yielding (topic, parsed_message) tuples."""
        ...
