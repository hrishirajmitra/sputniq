import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from sputniq.state.stores import SessionStore, MetadataStore


@pytest.mark.asyncio
async def test_session_store_redis(monkeypatch):
    store = SessionStore()
    
    mock_redis_client = AsyncMock()
    mock_redis_client.set = AsyncMock()
    mock_redis_client.get = AsyncMock(return_value='{"status": "running"}')
    
    with patch("redis.asyncio.from_url", return_value=mock_redis_client) as mock_from_url:
        await store.connect()
        mock_from_url.assert_called_once_with("redis://localhost:6379", decode_responses=True)
        
        await store.save_session("session-123", {"status": "running"})
        mock_redis_client.set.assert_called_once_with("session:session-123", '{"status": "running"}')
        
        result = await store.get_session("session-123")
        mock_redis_client.get.assert_called_once_with("session:session-123")
        assert result == {"status": "running"}
        
        await store.disconnect()

@pytest.mark.asyncio
async def test_session_store_unconnected():
    store = SessionStore()
    with pytest.raises(RuntimeError):
        await store.save_session("test", {})
    with pytest.raises(RuntimeError):
        await store.get_session("test")

@pytest.mark.asyncio
async def test_metadata_store_postgres(monkeypatch):
    store = MetadataStore()
    
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"data": '{"agent_id": "test"}'})
    
    # Magic to mock async with pool.acquire() as conn
    class AcquireContext:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
    mock_pool.acquire = MagicMock(return_value=AcquireContext())
    
    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.return_value = mock_pool
        await store.connect()
        mock_create_pool.assert_called_once_with(dsn="postgresql://sputniq:sputniq@localhost/sputniq")
        
        await store.save_metadata("corr-id", {"agent_id": "test"})
        mock_conn.execute.assert_called_once()
        
        result = await store.get_metadata("corr-id")
        mock_conn.fetchrow.assert_called_once()
        assert result == {"agent_id": "test"}
        
        await store.disconnect()

@pytest.mark.asyncio
async def test_metadata_store_unconnected():
    store = MetadataStore()
    with pytest.raises(RuntimeError):
        await store.save_metadata("test", {})
    with pytest.raises(RuntimeError):
        await store.get_metadata("test")