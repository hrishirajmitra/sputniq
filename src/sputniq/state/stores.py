from typing import Any
import json
import redis.asyncio as redis

class SessionStore:
    """Manages session state using Redis adapter for Phase 3.2."""
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self._redis = None

    async def connect(self):
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)

    async def disconnect(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def save_session(self, session_id: str, state: dict[str, Any]) -> None:
        """Stores state as JSON string mapping to session hash."""
        if not self._redis:
            raise RuntimeError("SessionStore not connected")
        await self._redis.set(f"session:{session_id}", json.dumps(state))

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Retrieves and parses session state."""
        if not self._redis:
            raise RuntimeError("SessionStore not connected")
        data = await self._redis.get(f"session:{session_id}")
        if data:
            return json.loads(data)
        return None

class MetadataStore:
    """Manages historical metadata via PostgreSQL (Mocked with asyncpg structures) for Phase 3.2"""
    def __init__(self, dsn: str = "postgresql://sputniq:sputniq@localhost/sputniq"):
        self.dsn = dsn
        self._pool = None

    async def connect(self):
        import asyncpg
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=self.dsn)

    async def disconnect(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def save_metadata(self, correlation_id: str, metadata: dict[str, Any]) -> None:
        if not self._pool:
            raise RuntimeError("MetadataStore not connected")
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO run_metadata (correlation_id, data) VALUES ($1, $2)",
                correlation_id, json.dumps(metadata)
            )

    async def get_metadata(self, correlation_id: str) -> dict[str, Any] | None:
        if not self._pool:
            raise RuntimeError("MetadataStore not connected")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM run_metadata WHERE correlation_id = $1", correlation_id
            )
            if row:
                return json.loads(row["data"])
            return None
