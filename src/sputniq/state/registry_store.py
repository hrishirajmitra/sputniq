"""Persistent registry store backed by PostgreSQL.

Stores workflow definitions, tool definitions, and app deployment records
in PostgreSQL using JSONB columns, replacing the previous in-memory dictionaries.
"""

import json
import logging
import os
from typing import Any

from sputniq.models.tools import ToolDefinition
from sputniq.models.workflows import WorkflowDefinition

logger = logging.getLogger(__name__)

_DEFAULT_DSN = "postgresql://sputniq:sputniq@localhost:5432/sputniq"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS registry_workflows (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS registry_tools (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS registry_apps (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""


class RegistryStore:
    """PostgreSQL-backed persistent registry for workflows, tools, and apps.

    Uses asyncpg connection pooling and stores Pydantic models as JSONB.
    Tables are auto-created on ``connect()``.
    """

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get("DATABASE_URL", _DEFAULT_DSN)
        self._pool = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Create the connection pool and ensure tables exist."""
        import asyncpg

        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=self.dsn)
            await self._init_tables()
            logger.info("RegistryStore connected and tables initialised.")

    async def disconnect(self) -> None:
        """Gracefully close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("RegistryStore disconnected.")

    async def _init_tables(self) -> None:
        """Run schema DDL to ensure all registry tables exist."""
        async with self._pool.acquire() as conn:
            await conn.execute(_INIT_SQL)

    def _ensure_connected(self) -> None:
        if not self._pool:
            raise RuntimeError("RegistryStore not connected")

    # ── Workflow CRUD ──────────────────────────────────────────────────────

    async def save_workflow(self, workflow: WorkflowDefinition) -> None:
        """Insert or update a workflow definition."""
        self._ensure_connected()
        data = workflow.model_dump(mode="json")
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO registry_workflows (id, data, updated_at)
                   VALUES ($1, $2::jsonb, NOW())
                   ON CONFLICT (id) DO UPDATE SET data = $2::jsonb, updated_at = NOW()""",
                workflow.id,
                json.dumps(data),
            )

    async def get_workflow(self, workflow_id: str) -> WorkflowDefinition | None:
        """Retrieve a workflow definition by ID, or None if not found."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM registry_workflows WHERE id = $1", workflow_id
            )
            if row:
                return WorkflowDefinition.model_validate_json(row["data"])
            return None

    async def list_workflows(self) -> list[WorkflowDefinition]:
        """Return all registered workflow definitions."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT data FROM registry_workflows ORDER BY id")
            return [WorkflowDefinition.model_validate_json(r["data"]) for r in rows]

    async def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow by ID. Returns True if a row was deleted."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM registry_workflows WHERE id = $1", workflow_id
            )
            return result == "DELETE 1"

    # ── Tool CRUD ──────────────────────────────────────────────────────────

    async def save_tool(self, tool: ToolDefinition) -> None:
        """Insert or update a tool definition."""
        self._ensure_connected()
        data = tool.model_dump(mode="json", by_alias=True)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO registry_tools (id, data, updated_at)
                   VALUES ($1, $2::jsonb, NOW())
                   ON CONFLICT (id) DO UPDATE SET data = $2::jsonb, updated_at = NOW()""",
                tool.id,
                json.dumps(data),
            )

    async def get_tool(self, tool_id: str) -> ToolDefinition | None:
        """Retrieve a tool definition by ID, or None if not found."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM registry_tools WHERE id = $1", tool_id
            )
            if row:
                return ToolDefinition.model_validate_json(row["data"])
            return None

    async def list_tools(self) -> list[ToolDefinition]:
        """Return all registered tool definitions."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT data FROM registry_tools ORDER BY id")
            return [ToolDefinition.model_validate_json(r["data"]) for r in rows]

    async def delete_tool(self, tool_id: str) -> bool:
        """Delete a tool by ID. Returns True if a row was deleted."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM registry_tools WHERE id = $1", tool_id
            )
            return result == "DELETE 1"

    # ── App CRUD ───────────────────────────────────────────────────────────

    async def save_app(self, app_id: str, app_data: dict[str, Any]) -> None:
        """Insert or update an app deployment record."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO registry_apps (id, data, updated_at)
                   VALUES ($1, $2::jsonb, NOW())
                   ON CONFLICT (id) DO UPDATE SET data = $2::jsonb, updated_at = NOW()""",
                app_id,
                json.dumps(app_data),
            )

    async def get_app(self, app_id: str) -> dict[str, Any] | None:
        """Retrieve an app deployment record by ID."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM registry_apps WHERE id = $1", app_id
            )
            if row:
                return json.loads(row["data"])
            return None

    async def list_apps(self) -> list[dict[str, Any]]:
        """Return all app deployment records."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT data FROM registry_apps ORDER BY id")
            return [json.loads(r["data"]) for r in rows]

    async def delete_app(self, app_id: str) -> bool:
        """Delete an app record by ID. Returns True if a row was deleted."""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM registry_apps WHERE id = $1", app_id
            )
            return result == "DELETE 1"
