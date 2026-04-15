"""Tests for RegistryStore — PostgreSQL-backed persistent registry."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sputniq.state.registry_store import RegistryStore
from sputniq.models.workflows import WorkflowDefinition, WorkflowStep
from sputniq.models.tools import ToolDefinition


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_workflow(wf_id: str = "test-wf") -> WorkflowDefinition:
    return WorkflowDefinition(
        id=wf_id,
        description="A test workflow",
        entrypoint_step="step-1",
        steps=[WorkflowStep(id="step-1", type="agent", ref="agent-1")],
    )


def _make_tool(tool_id: str = "test-tool") -> ToolDefinition:
    return ToolDefinition(id=tool_id, entrypoint="module:func")


class _AcquireContext:
    """Mock async context manager for ``pool.acquire()``."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


@pytest.fixture
def mock_pool_and_conn():
    """Shared fixture: returns (mock_pool, mock_conn) wired together."""
    mock_conn = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.acquire = MagicMock(return_value=_AcquireContext(mock_conn))
    return mock_pool, mock_conn


@pytest.fixture
def store(mock_pool_and_conn):
    """Returns a connected RegistryStore backed by mocked asyncpg pool."""
    mock_pool, _ = mock_pool_and_conn
    s = RegistryStore(dsn="postgresql://test:test@localhost/test")
    s._pool = mock_pool
    return s


# ── Lifecycle ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_connect_creates_pool_and_tables():
    store = RegistryStore(dsn="postgresql://test:test@localhost/test")
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire = MagicMock(return_value=_AcquireContext(mock_conn))

    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_pool
        await store.connect()

        mock_create.assert_called_once_with(dsn="postgresql://test:test@localhost/test")
        # _init_tables should have called execute with DDL
        mock_conn.execute.assert_called_once()
        assert "CREATE TABLE" in mock_conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_disconnect():
    store = RegistryStore()
    mock_pool = AsyncMock()
    store._pool = mock_pool

    await store.disconnect()

    mock_pool.close.assert_called_once()
    assert store._pool is None


@pytest.mark.asyncio
async def test_operations_raise_when_not_connected():
    store = RegistryStore()
    with pytest.raises(RuntimeError, match="not connected"):
        await store.save_workflow(_make_workflow())
    with pytest.raises(RuntimeError, match="not connected"):
        await store.get_workflow("x")
    with pytest.raises(RuntimeError, match="not connected"):
        await store.list_workflows()
    with pytest.raises(RuntimeError, match="not connected"):
        await store.save_tool(_make_tool())
    with pytest.raises(RuntimeError, match="not connected"):
        await store.get_tool("x")
    with pytest.raises(RuntimeError, match="not connected"):
        await store.list_tools()
    with pytest.raises(RuntimeError, match="not connected"):
        await store.save_app("x", {})
    with pytest.raises(RuntimeError, match="not connected"):
        await store.get_app("x")
    with pytest.raises(RuntimeError, match="not connected"):
        await store.list_apps()


# ── Workflow CRUD ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_workflow(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    wf = _make_workflow("wf-save")

    await store.save_workflow(wf)

    mock_conn.execute.assert_called_once()
    sql = mock_conn.execute.call_args[0][0]
    assert "INSERT INTO registry_workflows" in sql
    assert mock_conn.execute.call_args[0][1] == "wf-save"


@pytest.mark.asyncio
async def test_get_workflow_found(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    wf = _make_workflow("wf-found")
    mock_conn.fetchrow = AsyncMock(
        return_value={"data": wf.model_dump_json()}
    )

    result = await store.get_workflow("wf-found")

    assert result is not None
    assert result.id == "wf-found"
    mock_conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_get_workflow_not_found(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await store.get_workflow("no-such-wf")

    assert result is None


@pytest.mark.asyncio
async def test_list_workflows(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    wf1 = _make_workflow("wf-a")
    wf2 = _make_workflow("wf-b")
    mock_conn.fetch = AsyncMock(
        return_value=[
            {"data": wf1.model_dump_json()},
            {"data": wf2.model_dump_json()},
        ]
    )

    result = await store.list_workflows()

    assert len(result) == 2
    assert result[0].id == "wf-a"
    assert result[1].id == "wf-b"


@pytest.mark.asyncio
async def test_delete_workflow(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    mock_conn.execute = AsyncMock(return_value="DELETE 1")

    deleted = await store.delete_workflow("wf-del")

    assert deleted is True


@pytest.mark.asyncio
async def test_delete_workflow_not_found(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    mock_conn.execute = AsyncMock(return_value="DELETE 0")

    deleted = await store.delete_workflow("nope")

    assert deleted is False


# ── Tool CRUD ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_tool(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    tool = _make_tool("tool-save")

    await store.save_tool(tool)

    sql = mock_conn.execute.call_args[0][0]
    assert "INSERT INTO registry_tools" in sql


@pytest.mark.asyncio
async def test_get_tool_found(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    tool = _make_tool("tool-found")
    mock_conn.fetchrow = AsyncMock(
        return_value={"data": tool.model_dump_json(by_alias=True)}
    )

    result = await store.get_tool("tool-found")

    assert result is not None
    assert result.id == "tool-found"


@pytest.mark.asyncio
async def test_get_tool_not_found(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await store.get_tool("no-such")

    assert result is None


@pytest.mark.asyncio
async def test_list_tools(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    t1 = _make_tool("tool-a")
    t2 = _make_tool("tool-b")
    mock_conn.fetch = AsyncMock(
        return_value=[
            {"data": t1.model_dump_json(by_alias=True)},
            {"data": t2.model_dump_json(by_alias=True)},
        ]
    )

    result = await store.list_tools()

    assert len(result) == 2


# ── App CRUD ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_app(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn

    await store.save_app("app-1", {"app_id": "app-1", "version": "1.0"})

    sql = mock_conn.execute.call_args[0][0]
    assert "INSERT INTO registry_apps" in sql


@pytest.mark.asyncio
async def test_get_app_found(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    mock_conn.fetchrow = AsyncMock(
        return_value={"data": json.dumps({"app_id": "myapp", "version": "2.0"})}
    )

    result = await store.get_app("myapp")

    assert result == {"app_id": "myapp", "version": "2.0"}


@pytest.mark.asyncio
async def test_get_app_not_found(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await store.get_app("no-app")

    assert result is None


@pytest.mark.asyncio
async def test_list_apps(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    mock_conn.fetch = AsyncMock(
        return_value=[
            {"data": json.dumps({"app_id": "a1"})},
            {"data": json.dumps({"app_id": "a2"})},
        ]
    )

    result = await store.list_apps()

    assert len(result) == 2
    assert result[0]["app_id"] == "a1"


@pytest.mark.asyncio
async def test_delete_app(store, mock_pool_and_conn):
    _, mock_conn = mock_pool_and_conn
    mock_conn.execute = AsyncMock(return_value="DELETE 1")

    deleted = await store.delete_app("app-del")

    assert deleted is True
