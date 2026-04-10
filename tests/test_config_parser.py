"""Tests for config parser — Phase 1.2."""

from pathlib import Path

import pytest

from sputniq.config.errors import (
    BuildValidationError,
    ConfigLoadError,
    CyclicDependencyError,
    ReferenceError,
    ValidationError,
)
from sputniq.config.parser import detect_cycles, load_config, resolve_references
from sputniq.generator.validation import validate_source_tree
from sputniq.models.platform import SputniqConfig


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


class TestConfigParser:
    def test_load_config_valid(self, fixtures_dir: Path):
        config_path = fixtures_dir / "valid_config.json"
        config = load_config(config_path)

        assert isinstance(config, SputniqConfig)
        assert config.platform.name == "agentos-test"
        assert len(config.agents) == 1
        assert config.agents[0].id == "research-agent"
        assert len(config.workflows) == 1

    def test_load_config_not_found(self):
        with pytest.raises(ConfigLoadError, match="Configuration file not found"):
            load_config("nonexistent.json")

    def test_load_config_invalid_json(self, tmp_path: Path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{ this is not json }")

        with pytest.raises(ConfigLoadError, match="Failed to parse JSON"):
            load_config(bad_json)

    def test_resolve_references_valid(self, fixtures_dir: Path):
        config_path = fixtures_dir / "valid_config.json"
        config = load_config(config_path)
        # Should not raise
        resolve_references(config)

    def test_resolve_references_broken(self, fixtures_dir: Path):
        config_path = fixtures_dir / "broken_refs_config.json"
        config = load_config(config_path)

        with pytest.raises(ReferenceError, match="references unknown model"):
            resolve_references(config)

    def test_detect_cycles_valid(self, fixtures_dir: Path):
        config_path = fixtures_dir / "valid_config.json"
        config = load_config(config_path)
        # Should not raise
        detect_cycles(config)

    def test_detect_cycles_circular(self, fixtures_dir: Path):
        config_path = fixtures_dir / "circular_deps_config.json"
        config = load_config(config_path)

        with pytest.raises(CyclicDependencyError, match="Cycle detected"):
            detect_cycles(config)

    def test_resolve_references_requires_function_calling_for_tool_agents(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            """
            {
              "platform": {"name": "demo"},
              "agents": [{"id": "agent-a", "entrypoint": "src/agents/a.py:A", "model": "m1", "tools": ["tool-a"]}],
              "tools": [{"id": "tool-a", "entrypoint": "src/tools/t.py:tool_a"}],
              "models": [{"id": "m1", "provider": "openai", "capabilities": ["chat"]}],
              "workflows": [{"id": "wf", "entrypoint_step": "s1", "steps": [{"id": "s1", "type": "agent", "ref": "agent-a"}]}]
            }
            """,
            encoding="utf-8",
        )
        config = load_config(config_path)
        with pytest.raises(ValidationError, match="function-calling"):
            resolve_references(config)

    def test_validate_source_tree_missing_entrypoint(self, fixtures_dir: Path):
        config = load_config(fixtures_dir / "valid_config.json")
        with pytest.raises(BuildValidationError, match="entrypoint file not found"):
            validate_source_tree(config, fixtures_dir / "missing-root")
