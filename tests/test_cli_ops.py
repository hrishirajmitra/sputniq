
from click.testing import CliRunner

from sputniq.cli.main import cli


def test_cli_logs_all() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["logs"])
    assert result.exit_code == 0
    assert "Fetching logs for all" in result.output
    assert "Starting agent loop" in result.output

def test_cli_logs_specific() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "my-agent"])
    assert result.exit_code == 0
    assert "Fetching logs for my-agent" in result.output
    assert "- Starting agent loop" in result.output

def test_cli_status() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "AgentOS Status" in result.output
    assert "Active Orchestrations" in result.output
    assert "Healthy Services" in result.output
