"""AgentOS CLI — agentos init | validate | build."""

import json
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from sputniq.config.errors import ConfigError
from sputniq.config.parser import detect_cycles, load_config, resolve_references
from sputniq.generator.engine import generate_build_artifacts

console = Console()

_SAMPLE_CONFIG = {
    "platform": {
        "name": "my-agent-system",
        "version": "0.1.0",
        "namespace": "default",
        "runtime": "docker-compose",
        "region": "local",
    },
    "agents": [
        {
            "id": "my-agent",
            "description": "Describe your agent here",
            "entrypoint": "src/agents/my_agent.py:MyAgent",
            "model": "gpt-4o",
            "tools": ["my-tool"],
        }
    ],
    "tools": [
        {
            "id": "my-tool",
            "entrypoint": "src/tools/my_tool.py:my_tool",
            "schema": {
                "input": {"query": {"type": "string"}},
                "output": {"result": {"type": "string"}},
            },
        }
    ],
    "models": [{"id": "gpt-4o", "provider": "openai", "capabilities": ["chat"]}],
    "workflows": [
        {
            "id": "main-workflow",
            "entrypoint_step": "step-1",
            "steps": [{"id": "step-1", "type": "agent", "ref": "my-agent"}],
        }
    ],
    "infrastructure": {"secrets": ["OPENAI_API_KEY"]},
}


@click.group()
def cli() -> None:
    """AgentOS — config-driven orchestration for agentic AI systems."""


@cli.command()
@click.argument("directory", default=".", type=click.Path())
def init(directory: str) -> None:
    """Scaffold a new AgentOS project."""
    project_dir = Path(directory)
    config_path = project_dir / "config.json"

    if config_path.exists():
        console.print("[yellow]config.json already exists — skipping.[/yellow]")
        return

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "agents").mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "tools").mkdir(parents=True, exist_ok=True)

    config_path.write_text(json.dumps(_SAMPLE_CONFIG, indent=2), "utf-8")

    console.print(Panel.fit(
        "[green]✓[/green] Project initialised.\n\n"
        f"  [bold]config.json[/bold] written to [cyan]{project_dir.resolve()}[/cyan]\n"
        "  Edit it, then run [bold]agentos validate[/bold].",
        title="AgentOS init",
    ))


@cli.command()
@click.option("--config", "config_path", default="config.json", show_default=True,
              type=click.Path(exists=False), help="Path to config.json")
def validate(config_path: str) -> None:
    """Validate a config file — schema, references, and cycles."""
    try:
        config = load_config(Path(config_path))
        resolve_references(config)
        detect_cycles(config)
        console.print(f"[green]✓[/green] [bold]{config_path}[/bold] is valid.")
    except ConfigError as e:
        console.print(f"[red]✗[/red] Validation failed: {e}")
        raise SystemExit(1) from e


@cli.command()
@click.option("--config", "config_path", default="config.json", show_default=True,
              type=click.Path(exists=False), help="Path to config.json")
@click.option("--out", "output_dir", default=".agentos/build", show_default=True,
              help="Output directory for build artifacts")
def build(config_path: str, output_dir: str) -> None:
    """Validate config and generate service build artifacts."""
    try:
        config = load_config(Path(config_path))
        resolve_references(config)
        detect_cycles(config)
    except ConfigError as e:
        console.print(f"[red]✗[/red] Validation failed: {e}")
        raise SystemExit(1) from e

    out = Path(output_dir)
    manifest = generate_build_artifacts(config, out)

    service_count = len(manifest["services"])
    console.print(Panel.fit(
        f"[green]✓[/green] Build complete.\n\n"
        f"  Services generated : [bold]{service_count}[/bold]\n"
        f"  Output directory   : [cyan]{out.resolve()}[/cyan]",
        title="AgentOS build",
    ))
