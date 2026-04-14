"""Tests for the service artifact generator — Phase 1.3."""

import json
from pathlib import Path

import pytest

from sputniq.config.parser import load_config
from sputniq.generator.engine import generate_build_artifacts


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def build_output(tmp_path: Path, fixtures_dir: Path) -> dict:
    config = load_config(fixtures_dir / "valid_config.json")
    manifest = generate_build_artifacts(config, tmp_path)
    return {"manifest": manifest, "out": tmp_path, "config": config}


class TestGeneratorEngine:
    def test_manifest_keys(self, build_output: dict):
        m = build_output["manifest"]
        assert "platform" in m
        assert "version" in m
        assert "services" in m
        assert "built_at" in m

    def test_manifest_file_written(self, build_output: dict):
        manifest_path = build_output["out"] / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["platform"] == "agentos-test"

    def test_agent_service_dir_created(self, build_output: dict):
        out = build_output["out"]
        assert (out / "services" / "research-agent").is_dir()

    def test_tool_service_dir_created(self, build_output: dict):
        out = build_output["out"]
        assert (out / "services" / "web-search").is_dir()

    def test_dockerfile_generated(self, build_output: dict):
        dockerfile = build_output["out"] / "services" / "research-agent" / "Dockerfile"
        assert dockerfile.exists()
        content = dockerfile.read_text()
        assert "FROM python:3.11-slim" in content
        assert "research-agent" in content

    def test_service_yaml_generated(self, build_output: dict):
        service_yaml = build_output["out"] / "services" / "research-agent" / "service.yaml"
        assert service_yaml.exists()
        content = service_yaml.read_text()
        assert "research-agent" in content

    def test_requirements_txt_generated(self, build_output: dict):
        req = build_output["out"] / "services" / "research-agent" / "requirements.txt"
        assert req.exists()
        assert "pydantic" in req.read_text()

    def test_tool_schemas_written(self, build_output: dict):
        schemas_path = build_output["out"] / "schemas" / "tool-schemas.json"
        assert schemas_path.exists()
        schemas = json.loads(schemas_path.read_text())
        assert "web-search" in schemas

    def test_model_endpoints_written(self, build_output: dict):
        schemas_path = build_output["out"] / "schemas" / "model-endpoints.json"
        assert schemas_path.exists()
        schemas = json.loads(schemas_path.read_text())
        assert "gpt-4o" in schemas

    def test_orchestration_graphs_written(self, build_output: dict):
        graphs_path = build_output["out"] / "orchestrations" / "graphs.json"
        assert graphs_path.exists()
        graphs = json.loads(graphs_path.read_text())
        assert "qa-pipeline" in graphs

    def test_manifest_entities(self, build_output: dict):
        entities = build_output["manifest"]["entities"]
        assert entities["agents"] == ["research-agent"]
        assert entities["tools"] == ["web-search"]
        assert entities["models"] == ["gpt-4o"]
        assert entities["orchestrations"] == ["qa-pipeline"]
