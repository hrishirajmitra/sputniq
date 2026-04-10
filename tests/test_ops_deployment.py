import json
import pytest
from pathlib import Path

from sputniq.ops.deployment import DeploymentEngine

@pytest.fixture
def mock_templates(tmp_path):
    d = tmp_path / "templates"
    d.mkdir()
    template_content = """# Platform: {{ platform.name }}
services:
{% for service in services %}
  {{ service.id }}:
    image: {{ service.image }}
{% endfor %}"""
    d.joinpath("deployment-docker-compose.yaml.j2").write_text(template_content)
    return d

@pytest.fixture
def mock_build_manifest(tmp_path):
    d = tmp_path / "build"
    d.mkdir()
    manifest = {
        "version": "1.0",
        "services": [
            {"id": "agent-one", "image": "registry/agent-one:latest"},
            {"id": "agent-two", "image": "registry/agent-two:latest"}
        ]
    }
    d.joinpath("build.manifest.json").write_text(json.dumps(manifest))
    return d.joinpath("build.manifest.json")

def test_deployment_engine_docker_compose(mock_templates, mock_build_manifest, tmp_path):
    engine = DeploymentEngine(mock_templates)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    
    platform_config = {"name": "test-os", "runtime": "docker-compose"}
    
    output_file = engine.render_manifest(platform_config, mock_build_manifest, out_dir)
    
    assert output_file.exists()
    assert output_file.name == "deployment-docker-compose.yaml"
    
    content = output_file.read_text()
    assert "# Platform: test-os" in content
    assert "agent-one:" in content
    assert "image: registry/agent-one:latest" in content
    assert "agent-two:" in content

def test_deployment_engine_missing_template(tmp_path, mock_build_manifest):
    d = tmp_path / "empty_templates"
    d.mkdir()
    
    engine = DeploymentEngine(d)
    platform_config = {"name": "k8s-os", "runtime": "kubernetes"}
    
    with pytest.raises(FileNotFoundError, match="Missing deployment-kubernetes.yaml.j2"):
        engine.render_manifest(platform_config, mock_build_manifest, tmp_path)
