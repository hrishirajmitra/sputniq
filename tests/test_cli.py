"""Tests for CLI commands — Phase 1.4."""

import json
from pathlib import Path

from click.testing import CliRunner

from sputniq.cli.main import cli


class TestCLIInit:
    def test_init_creates_files(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(cli, ["init", str(tmp_path)])

        assert result.exit_code == 0
        assert (tmp_path / "config.json").exists()
        assert (tmp_path / "src" / "agents").is_dir()
        assert (tmp_path / "src" / "tools").is_dir()

    def test_init_valid_config(self, tmp_path: Path):
        runner = CliRunner()
        runner.invoke(cli, ["init", str(tmp_path)])

        data = json.loads((tmp_path / "config.json").read_text())
        assert "platform" in data
        assert "agents" in data

    def test_init_skips_existing(self, tmp_path: Path):
        runner = CliRunner()
        (tmp_path / "config.json").write_text('{"platform": {"name": "existing"}}')
        result = runner.invoke(cli, ["init", str(tmp_path)])

        assert result.exit_code == 0
        assert "already exists" in result.output


class TestCLIValidate:
    def test_validate_valid_config(self):
        runner = CliRunner()
        valid = Path(__file__).parent / "fixtures" / "valid_config.json"
        result = runner.invoke(cli, ["validate", "--config", str(valid)])

        assert result.exit_code == 0
        assert "is valid" in result.output

    def test_validate_missing_file(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--config", str(tmp_path / "nope.json")])

        assert result.exit_code == 1

    def test_validate_broken_refs(self):
        runner = CliRunner()
        broken = Path(__file__).parent / "fixtures" / "broken_refs_config.json"
        result = runner.invoke(cli, ["validate", "--config", str(broken)])

        assert result.exit_code == 1
        assert "Validation failed" in result.output

    def test_validate_circular_deps(self):
        runner = CliRunner()
        circular = Path(__file__).parent / "fixtures" / "circular_deps_config.json"
        result = runner.invoke(cli, ["validate", "--config", str(circular)])

        assert result.exit_code == 1


class TestCLIBuild:
    def test_build_produces_artifacts(self, tmp_path: Path):
        runner = CliRunner()
        valid = Path(__file__).parent / "fixtures" / "valid_config.json"
        out = tmp_path / "build"
        result = runner.invoke(cli, [
            "build",
            "--config", str(valid),
            "--out", str(out),
        ])

        assert result.exit_code == 0
        assert (out / "manifest.json").exists()
        assert (out / "services" / "research-agent").is_dir()
