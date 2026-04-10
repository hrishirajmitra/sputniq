import json
import logging
from typing import Any, AsyncIterator

import aiokafka
from pydantic import BaseModel

from .base import MessageConsumer, MessageProducer

logger = logging.getLogger(__name__)

class KafkaMessageProducer(MessageProducer):
    def __init__(self, bootstrap_servers: str | list[str] = "localhost:9092"):
        if isinstance(bootstrap_servers, list):
            bootstrap_servers = ",".join(bootstrap_servers)
        self.bootstrap_servers = bootstrap_servers
        self._producer: aiokafka.AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = aiokafka.AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, message: dict[str, Any] | BaseModel) -> None:
        if not self._producer:
            raise RuntimeError("Producer must be started before publishing.")
        if isinstance(message, BaseModel):
            data = message.model_dump()
        else:
            data = message
        await self._producer.send_and_wait(topic, data)


class KafkaMessageConsumer(MessageConsumer):
    def __init__(self, topics: str | list[str], bootstrap_servers: str | list[str] = "localhost:9092", group_id: str = "sputniq-group"):
        self.bootstrap_servers = bootstrap_servers if isinstance(bootstrap_servers, str) else ",".join(bootstrap_servers)
        self.group_id = group_id
        if isinstance(topics, str):
            topics = [topics]
        self.topics = topics
        self._consumer: aiokafka.AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self._consumer = aiokafka.AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        await self._consumer.start()

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None

    async def consume(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        if not self._consumer:
            raise RuntimeError("Consumer must be started before consuming.")
        async for msg in self._consumer:
            yield msg.topic, msg.value
