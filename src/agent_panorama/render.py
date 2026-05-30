"""Render a :class:`Report` to Markdown and self-contained HTML via Jinja2."""

from __future__ import annotations

from datetime import datetime

from jinja2 import Environment, PackageLoader

from .config import ReportConfig
from .models import AgentRun, Report

_TEMPLATES = {"md": "report.md.j2", "html": "report.html.j2"}


def _autoescape(template_name: str | None) -> bool:
    """Enable autoescaping only for HTML templates (not Markdown)."""
    return bool(template_name and "html" in template_name)


def _environment() -> Environment:
    """Create the Jinja2 environment with the package's template loader."""
    env = Environment(
        loader=PackageLoader("agent_panorama", "templates"),
        autoescape=_autoescape,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fmt_time"] = _fmt_time
    env.filters["fmt_int"] = _fmt_int
    return env


def render(report: Report, config: ReportConfig, output_format: str) -> str:
    """Render a report to the requested format.

    Args:
        report: The assembled report.
        config: Report configuration (used for plain-English tool naming).
        output_format: Either ``"md"`` or ``"html"``.

    Returns:
        The rendered document as a string.

    Raises:
        ValueError: If ``output_format`` is not supported.
    """
    if output_format not in _TEMPLATES:
        supported = ", ".join(sorted(_TEMPLATES))
        raise ValueError(f"Unsupported format '{output_format}'. Supported: {supported}.")
    template = _environment().get_template(_TEMPLATES[output_format])
    return template.render(report=report, config=config, summaries=_run_summaries(report, config))


def _run_summaries(report: Report, config: ReportConfig) -> dict[str, list[str]]:
    """Pre-compute plain-English action lists keyed by run id."""
    return {run.run_id: _describe_actions(run, config) for run in report.runs}


def _describe_actions(run: AgentRun, config: ReportConfig) -> list[str]:
    """Render each tool call of a run as a plain-English sentence."""
    from .analysis import summarize_arguments

    lines: list[str] = []
    for call in run.tool_calls:
        action = config.describe_tool(call.name)
        params = summarize_arguments(call.arguments)
        suffix = "" if call.succeeded else " (failed)"
        detail = f" — {params}" if params and params != "—" else ""
        lines.append(f"{action}{detail}{suffix}")
    return lines


def _fmt_time(value: datetime | None) -> str:
    """Format a datetime as a compact UTC string, or an em dash if missing."""
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_int(value: int) -> str:
    """Format an integer with thousands separators."""
    return f"{value:,}"
