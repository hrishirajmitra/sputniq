import json
from click.testing import CliRunner

from sputniq.cli.main import cli
from sputniq.ops.security import ArtifactManifest

def test_cli_package(tmp_path):
    runner = CliRunner()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    
    res = runner.invoke(cli, ["package", "--dir", str(build_dir)])
    
    assert res.exit_code == 0
    assert "scanning" in res.output.lower()
    assert "containerized successfully" in res.output.lower()
    
    assert build_dir.joinpath("build.manifest.json").exists()

def test_cli_deploy():
    runner = CliRunner()
    res = runner.invoke(cli, ["deploy", "--env", "prod"])
    
    assert res.exit_code == 0
    assert "deploying bundled manifest to prod" in res.output.lower()
    assert "target orchestration active" in res.output.lower()
