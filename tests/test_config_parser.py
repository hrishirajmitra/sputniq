"""Tests for config parser — Phase 1.2."""

from pathlib import Path

import pytest

from sputniq.config.errors import (
    ConfigLoadError,
    CyclicDependencyError,
    ReferenceError,
)
from sputniq.config.parser import detect_cycles, load_config, resolve_references
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
