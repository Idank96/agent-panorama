"""Command-line interface for agent-panorama."""

from __future__ import annotations

from pathlib import Path

import click

from . import __version__
from .core import generate_report


@click.group()
@click.version_option(__version__, prog_name="agent-panorama")
def cli() -> None:
    """Turn agent traces into human-readable Agent Activity Reports."""


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
def generate(
    input_path: Path,
    output_dir: Path,
    formats: str,
    input_type: str,
    config_path: Path | None,
) -> None:
    """Generate a report from a trace export."""
    selected = ["md", "html"] if formats == "both" else [formats]
    report = generate_report(
        input_path=input_path,
        output_dir=output_dir,
        formats=selected,
        input_type=input_type,
        config=config_path,
    )
    _print_summary(report, output_dir, selected)


def _print_summary(report, output_dir: Path, formats: list[str]) -> None:
    """Print a short confirmation summary of what was generated."""
    click.secho("✓ Agent Activity Report generated", fg="green", bold=True)
    click.echo(f"  Runs:    {report.total_runs}")
    click.echo(f"  Actions: {report.total_actions}")
    click.echo(f"  Tokens:  {report.total_tokens:,}")
    for fmt in formats:
        click.echo(f"  Wrote:   {output_dir / ('report.' + fmt)}")


if __name__ == "__main__":
    cli()
