"""Tests for Sputniq data models — Phase 1.1."""

import pytest
from pydantic import ValidationError

from sputniq.models import (
    AgentDefinition,
    AgentInput,
    AgentOutput,
    Error,
    HeartBeat,
    ModelDefinition,
    ModelRequest,
    ModelResponse,
    PlatformConfig,
    SputniqConfig,
    ToolDefinition,
    ToolRequest,
    ToolResponse,
    WorkflowComplete,
    WorkflowDefinition,
    WorkflowStepMessage,
)

# ── AgentDefinition ────────────────────────────────────────────────────────


class TestAgentDefinition:
    def test_valid_minimal(self):
        a = AgentDefinition(id="research-agent", entrypoint="src/a.py:A", model="gpt-4o")
        assert a.id == "research-agent"
        assert a.tools == []
        assert a.memory.type == "sliding-window"
        assert a.retry.max_attempts == 3

    def test_valid_full(self):
        a = AgentDefinition(
            id="research-agent",
            description="Searches the web",
            entrypoint="src/agents/research.py:ResearchAgent",
            model="gpt-4o",
            tools=["web-search", "summarizer"],
            memory={"type": "sliding-window", "max_tokens": 8192},
            system_prompt="You are a research assistant...",
            max_turns=20,
            timeout_ms=30000,
            retry={"max_attempts": 3, "backoff": "exponential"},
        )
        assert a.tools == ["web-search", "summarizer"]
        assert a.memory.max_tokens == 8192

    def test_invalid_id_format(self):
        with pytest.raises(ValidationError):
            AgentDefinition(id="Bad Agent!", entrypoint="a.py:A", model="m")

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            AgentDefinition(id="a")  # type: ignore[call-arg]

    def test_invalid_max_turns(self):
        with pytest.raises(ValidationError):
            AgentDefinition(id="a", entrypoint="a.py:A", model="m", max_turns=0)


# ── ToolDefinition ──────────────────────────────────────────────────────────


class TestToolDefinition:
    def test_valid_minimal(self):
        t = ToolDefinition(id="web-search", entrypoint="src/tools/search.py:search")
        assert t.timeout_ms == 10000
        assert t.rate_limit.requests_per_minute == 60

    def test_valid_with_schema(self):
        t = ToolDefinition(
            id="web-search",
            entrypoint="src/tools/search.py:search",
            schema={
                "input": {"query": {"type": "string"}},
                "output": {"results": {"type": "array"}},
            },
        )
        assert "query" in t.schema_def.input

    def test_invalid_id(self):
        with pytest.raises(ValidationError):
            ToolDefinition(id="", entrypoint="a.py:a")


# ── ModelDefinition ─────────────────────────────────────────────────────────


class TestModelDefinition:
    def test_valid_minimal(self):
        m = ModelDefinition(id="gpt-4o")
        assert m.provider == "openai"
        assert m.capabilities == ["chat"]

    def test_custom_provider(self):
        m = ModelDefinition(id="local-llama", provider="vllm", endpoint="http://localhost:8000")
        assert m.endpoint == "http://localhost:8000"

    def test_invalid_provider(self):
        with pytest.raises(ValidationError):
            ModelDefinition(id="m", provider="invalid")  # type: ignore[arg-type]


# ── WorkflowDefinition ─────────────────────────────────────────────────────


class TestWorkflowDefinition:
    def test_valid(self):
        w = WorkflowDefinition(
            id="qa-pipeline",
            entrypoint_step="step-1",
            steps=[
                {"id": "step-1", "type": "agent", "ref": "research-agent", "next": ["step-2"]},
                {"id": "step-2", "type": "tool", "ref": "web-search"},
            ],
        )
        assert len(w.steps) == 2

    def test_empty_steps(self):
        with pytest.raises(ValidationError):
            WorkflowDefinition(id="w", entrypoint_step="s", steps=[])


# ── Messages ────────────────────────────────────────────────────────────────


class TestMessages:
    def test_agent_input_defaults(self):
        msg = AgentInput(agent_id="a", payload="hello")
        assert msg.correlation_id  # auto-generated
        assert msg.timestamp_ns > 0

    def test_tool_request(self):
        msg = ToolRequest(tool_id="web-search", arguments={"query": "AI"})
        assert msg.arguments["query"] == "AI"

    def test_error_message(self):
        err = Error(
            error_code="TOOL_TIMEOUT",
            message="web-search timed out after 10000ms",
            entity_id="web-search",
            retryable=True,
            context={"query": "latest AI news"},
        )
        assert err.retryable is True
        assert err.error_code == "TOOL_TIMEOUT"

    def test_heartbeat(self):
        hb = HeartBeat(entity_id="research-agent")
        assert hb.status == "alive"

    def test_all_message_types_instantiate(self):
        """Smoke test: every message type can be created with minimal args."""
        AgentOutput(agent_id="a", result="ok")
        ToolResponse(tool_id="t", result={})
        ModelRequest(model_id="m", messages=[{"role": "user", "content": "hi"}])
        ModelResponse(model_id="m", content="hello")
        WorkflowStepMessage(workflow_id="w", step_id="s")
        WorkflowComplete(workflow_id="w")


# ── PlatformConfig & SputniqConfig ──────────────────────────────────────────


class TestPlatformConfig:
    def test_valid(self):
        p = PlatformConfig(name="my-platform")
        assert p.runtime == "docker-compose"
        assert p.namespace == "default"


class TestSputniqConfig:
    def test_minimal(self):
        cfg = SputniqConfig(platform={"name": "test"})
        assert cfg.agents == []
        assert cfg.infrastructure.message_bus == "kafka"

    def test_full_config(self):
        cfg = SputniqConfig(
            platform={"name": "test", "runtime": "kubernetes"},
            agents=[{"id": "a", "entrypoint": "a.py:A", "model": "gpt-4o"}],
            tools=[{"id": "t", "entrypoint": "t.py:t"}],
            models=[{"id": "gpt-4o"}],
            workflows=[
                {
                    "id": "w",
                    "entrypoint_step": "s1",
                    "steps": [{"id": "s1", "ref": "a", "type": "agent"}],
                }
            ],
        )
        assert len(cfg.agents) == 1
        assert cfg.platform.runtime == "kubernetes"
