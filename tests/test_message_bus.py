import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel

from sputniq.bus.kafka import KafkaMessageProducer, KafkaMessageConsumer

class DummyMessage(BaseModel):
    id: str
    content: str

@pytest.fixture
def mock_aiokafka_producer():
    with patch("sputniq.bus.kafka.aiokafka.AIOKafkaProducer") as mock:
        instance = mock.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        instance.send_and_wait = AsyncMock()
        yield mock

@pytest.fixture
def mock_aiokafka_consumer():
    with patch("sputniq.bus.kafka.aiokafka.AIOKafkaConsumer") as mock:
        instance = mock.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        # Mock async integration for `async for msg in consumer`
        class AsyncIterConfig:
            def __init__(self):
                self.messages = []
            def __aiter__(self, *_args, **_kwargs):
                self._iter = iter(self.messages)
                return self
            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration
                    
        iter_mock = AsyncIterConfig()
        def set_messages(msgs):
            iter_mock.messages = msgs
            
        instance.__aiter__ = iter_mock.__aiter__
        instance.set_messages = set_messages
        yield mock

@pytest.mark.asyncio
async def test_kafka_producer_lifecycle(mock_aiokafka_producer):
    producer = KafkaMessageProducer(bootstrap_servers="test-broker:9092")
    await producer.start()
    mock_aiokafka_producer.return_value.start.assert_called_once()
    
    await producer.stop()
    mock_aiokafka_producer.return_value.stop.assert_called_once()
    assert producer._producer is None

@pytest.mark.asyncio
async def test_kafka_producer_publish_dict(mock_aiokafka_producer):
    producer = KafkaMessageProducer()
    await producer.start()
    
    msg = {"hello": "world"}
    await producer.publish("test_topic", msg)
    
    mock_aiokafka_producer.return_value.send_and_wait.assert_called_once_with("test_topic", msg)

@pytest.mark.asyncio
async def test_kafka_producer_publish_pydantic(mock_aiokafka_producer):
    producer = KafkaMessageProducer()
    await producer.start()
    
    msg = DummyMessage(id="msg-1", content="Hello Pydantic")
    await producer.publish("test_topic", msg)
    
    expected_dict = {"id": "msg-1", "content": "Hello Pydantic"}
    mock_aiokafka_producer.return_value.send_and_wait.assert_called_once_with("test_topic", expected_dict)

@pytest.mark.asyncio
async def test_kafka_producer_publish_unstarted():
    producer = KafkaMessageProducer()
    with pytest.raises(RuntimeError, match="Producer must be started"):
        await producer.publish("topic", {})

@pytest.mark.asyncio
async def test_kafka_consumer_lifecycle(mock_aiokafka_consumer):
    consumer = KafkaMessageConsumer(topics=["topic-A"], bootstrap_servers="test-broker:9092")
    await consumer.start()
    mock_aiokafka_consumer.return_value.start.assert_called_once()
    
    await consumer.stop()
    mock_aiokafka_consumer.return_value.stop.assert_called_once()
    assert consumer._consumer is None

@pytest.mark.asyncio
async def test_kafka_consumer_consume(mock_aiokafka_consumer):
    consumer = KafkaMessageConsumer(topics=["topic-A"])
    await consumer.start()
    
    # Setup mock messages
    class MockMsg:
        def __init__(self, topic, value):
            self.topic = topic
            self.value = value
            
    mock_aiokafka_consumer.return_value.set_messages([
        MockMsg("topic-A", {"key": "val1"}),
        MockMsg("topic-A", {"key": "val2"})
    ])
    
    results = []
    async for topic, value in consumer.consume():
        results.append((topic, value))
        
    assert len(results) == 2
    assert results[0] == ("topic-A", {"key": "val1"})
    assert results[1] == ("topic-A", {"key": "val2"})

@pytest.mark.asyncio
async def test_kafka_consumer_unstarted():
    consumer = KafkaMessageConsumer(topics=["t1"])
    with pytest.raises(RuntimeError, match="Consumer must be started"):
        async for _ in consumer.consume():
            pass
