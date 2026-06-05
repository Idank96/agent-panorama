"""Command-line interface for agent-panorama."""

from __future__ import annotations

from pathlib import Path

import click

from . import __version__
from .config import ReportConfig, load_config
from .core import generate_report
from .models import Report


@click.group()
@click.version_option(__version__, prog_name="agent-panorama")
def cli() -> None:
    """Turn agent traces into human-readable Agent Activity Reports."""
    _load_dotenv()


def _load_dotenv() -> None:
    """Load a local .env (e.g. for GOOGLE_API_KEY) without overriding real env vars."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)


@cli.command()
@click.option(
    "--input",
    "inputs",
    required=True,
    multiple=True,
    type=str,
    help="Path, glob, or directory of Langfuse/LangSmith JSON exports. "
    "Repeatable; globs and directories are expanded (validated at load).",
)
@click.option(
    "--output",
    "output_dir",
    default="./report",
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to write the report into (default: ./report).",
)
@click.option(
    "--format",
    "formats",
    type=click.Choice(["md", "html", "json", "both"]),
    default="both",
    help="Output format(s) to write; 'both' = md+html (default: both).",
)
@click.option(
    "--input-type",
    type=click.Choice(["langfuse", "langsmith"]),
    default="langfuse",
    help="Trace export format (default: langfuse).",
)
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional YAML config mapping tool names and thresholds.",
)
@click.option(
    "--detail",
    type=click.Choice(["minimal", "standard", "richer"]),
    default="standard",
    help="Narrative detail per step (increasing): 'minimal' lists step names "
    "only, 'standard' adds a model-call hint, 'richer' adds tokens, duration, "
    "and error reasons (default: standard).",
)
@click.option(
    "--summarize",
    is_flag=True,
    default=False,
    help="Phrase each minimal-detail result via a cheap LLM (opt-in). Requires a "
    "provider extra installed and its API key set; see the README.",
)
@click.option(
    "--summarize-model",
    default=None,
    help="LangChain model id for --summarize, e.g. 'google_genai:gemini-2.5-flash-lite' "
    "or 'openai:gpt-5-nano' (default: google_genai:gemini-2.5-flash-lite).",
)
@click.option(
    "--session",
    default=None,
    help="Keep only runs matching this session id.",
)
@click.option(
    "--since",
    default=None,
    help="Keep only runs starting at/after this ISO date or datetime (UTC).",
)
@click.option(
    "--until",
    default=None,
    help="Keep only runs starting at/before this ISO date or datetime (UTC).",
)
def generate(
    inputs: tuple[str, ...],
    output_dir: Path,
    formats: str,
    input_type: str,
    config_path: Path | None,
    detail: str,
    summarize: bool,
    summarize_model: str | None,
    session: str | None,
    since: str | None,
    until: str | None,
) -> None:
    """Generate a report from one or more trace exports."""
    selected = ["md", "html"] if formats == "both" else [formats]
    try:
        report = generate_report(
            inputs=list(inputs),
            output_dir=output_dir,
            formats=selected,
            input_type=input_type,
            config=_config_with_model(config_path, summarize_model),
            detail=detail,
            summarize=summarize,
            session=session,
            since=since,
            until=until,
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    _print_summary(report, output_dir, selected, summarize)


def _config_with_model(
    config_path: Path | None, summarize_model: str | None
) -> ReportConfig | Path | None:
    """Return the config source, overriding the summarize model when given."""
    if summarize_model is None:
        return config_path
    config = load_config(config_path)
    config.summarize_model = summarize_model
    return config


def _print_summary(report: Report, output_dir: Path, formats: list[str], summarize: bool) -> None:
    """Print a short confirmation summary of what was generated."""
    click.secho("✓ Agent Activity Report generated", fg="green", bold=True)
    click.echo(f"  Runs:    {report.total_runs}")
    click.echo(f"  Agents:  {len(report.rollups)}")
    click.echo(f"  Steps:   {report.total_steps}")
    click.echo(f"  Tokens:  {report.total_tokens:,}")
    if report.total_cost_usd is not None:
        click.echo(f"  Cost:    ${report.total_cost_usd:.4f}")
    for fmt in formats:
        click.echo(f"  Wrote:   {output_dir / ('report.' + fmt)}")
    if summarize:
        click.echo(f"  LLM log: {output_dir / 'llm_calls.log'}")


@cli.command()
@click.option("--port", default=8321, type=int, help="Port to listen on (default: 8321).")
@click.option("--host", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1).")
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional YAML config mapping tool names and thresholds.",
)
@click.option(
    "--max-runs",
    default=None,
    type=int,
    help="Keep at most this many runs in memory (oldest trimmed first).",
)
@click.option(
    "--open",
    "open_browser",
    is_flag=True,
    default=False,
    help="Open the dashboard in the default browser on start.",
)
def serve(
    port: int,
    host: str,
    config_path: Path | None,
    max_runs: int | None,
    open_browser: bool,
) -> None:
    """Run the live dashboard server (requires the 'live' extra)."""
    try:
        from .live.server import serve as run_server
    except ImportError as error:
        raise click.ClickException(
            "Live mode needs extra dependencies. Install with: pip install 'agent-panorama[live]'"
        ) from error
    click.secho(f"agent-panorama live dashboard on http://{host}:{port}", fg="green", bold=True)
    click.echo("  Stream runs from your app with PanoramaCallbackHandler (Ctrl+C to stop).")
    try:
        run_server(
            port=port,
            host=host,
            config_path=config_path,
            max_runs=max_runs,
            open_browser=open_browser,
        )
    except OSError as error:
        raise click.ClickException(str(error)) from error


if __name__ == "__main__":
    cli()
