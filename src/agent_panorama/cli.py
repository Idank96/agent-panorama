"""Command-line interface for agent-panorama."""

from __future__ import annotations

from pathlib import Path

import click

from . import __version__
from .config import ReportConfig, load_config
from .core import generate_report


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
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the Langfuse/LangSmith JSON trace export.",
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
    type=click.Choice(["md", "html", "both"]),
    default="both",
    help="Output format(s) to write (default: both).",
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
def generate(
    input_path: Path,
    output_dir: Path,
    formats: str,
    input_type: str,
    config_path: Path | None,
    detail: str,
    summarize: bool,
    summarize_model: str | None,
) -> None:
    """Generate a report from a trace export."""
    selected = ["md", "html"] if formats == "both" else [formats]
    report = generate_report(
        input_path=input_path,
        output_dir=output_dir,
        formats=selected,
        input_type=input_type,
        config=_config_with_model(config_path, summarize_model),
        detail=detail,
        summarize=summarize,
    )
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


def _print_summary(report, output_dir: Path, formats: list[str], summarize: bool) -> None:
    """Print a short confirmation summary of what was generated."""
    click.secho("✓ Agent Activity Report generated", fg="green", bold=True)
    click.echo(f"  Runs:    {report.total_runs}")
    click.echo(f"  Steps:   {report.total_steps}")
    click.echo(f"  Tokens:  {report.total_tokens:,}")
    for fmt in formats:
        click.echo(f"  Wrote:   {output_dir / ('report.' + fmt)}")
    if summarize:
        click.echo(f"  LLM log: {output_dir / 'llm_calls.log'}")


if __name__ == "__main__":
    cli()
