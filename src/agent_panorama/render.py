"""Render a :class:`Report` to Markdown and self-contained HTML via Jinja2."""

from __future__ import annotations

import re
from datetime import datetime

from jinja2 import Environment, PackageLoader

from .config import ReportConfig
from .models import AgentRun, Report, Step

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


def _describe_steps(run: AgentRun, config: ReportConfig) -> list[str]:
    """Render a run's steps as an ordered, plain-English narrative.

    Detail grows ``minimal`` < ``standard`` < ``richer``: ``minimal`` shows only
    the step name; ``standard`` adds a model-call hint and failure marker;
    ``richer`` adds tokens, duration, tool-call count, and the error reason.
    """
    return [_describe_step(step, config) for step in run.steps]


def _describe_step(step: Step, config: ReportConfig) -> str:
    """Render a single step as one narrative line at the configured detail."""
    label = config.describe_tool(step.name)
    if config.detail == "minimal":
        return label
    hints = _rich_hints(step) if config.detail == "richer" else _standard_hints(step)
    suffix = f" ({' · '.join(hints)})" if hints else ""
    return f"{label}{suffix}{_failure_suffix(step, config.detail)}"


def _standard_hints(step: Step) -> list[str]:
    """Light activity hints for ``standard`` detail (model-call count only)."""
    if not step.model_calls:
        return []
    return [_count(step.model_calls, "model call")]


def _rich_hints(step: Step) -> list[str]:
    """Full activity hints for ``richer`` detail (calls, tokens, duration)."""
    hints: list[str] = []
    if step.model_calls:
        hints.append(_count(step.model_calls, "model call"))
    if step.tool_calls:
        hints.append(_count(step.tool_calls, "tool call"))
    if step.tokens:
        hints.append(f"{step.tokens:,} tokens")
    if step.duration_seconds is not None:
        hints.append(f"{step.duration_seconds:.1f}s")
    return hints


def _count(value: int, noun: str) -> str:
    """Pluralize a counted noun, e.g. ``1 model call`` / ``3 model calls``."""
    return f"{value} {noun}{'' if value == 1 else 's'}"


def _failure_suffix(step: Step, detail: str) -> str:
    """Append a failure marker, including the error reason in ``richer`` detail."""
    if step.succeeded:
        return ""
    if detail == "richer" and step.error:
        return f" — failed: {step.error}"
    return " — failed"


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
    return template.render(
        report=report,
        config=config,
        narratives={run.run_id: _describe_steps(run, config) for run in report.runs},
        results={run.run_id: _result_text(run, config.detail) for run in report.runs},
    )


# Max characters of a result shown on the standard/richer "Result:" line. The
# stored result is longer (so the LLM summarizer gets context); this clips it
# for readable display only.
_RESULT_DISPLAY_CHARS = 280


def _result_text(run: AgentRun, detail: str) -> str:
    """Render a run's result at the configured detail.

    ``minimal`` prefers an LLM action summary when present, else condenses the
    result to a single short sentence (dropping data tables and leading
    symbols); other levels clip the stored result for readable display.
    """
    if not run.output_text:
        return run.output_text
    if detail == "minimal":
        return run.result_summary or _condense(run.output_text)
    return _clip(run.output_text, _RESULT_DISPLAY_CHARS)


def _clip(text: str, max_chars: int) -> str:
    """Truncate text to ``max_chars`` with an ellipsis, on a word boundary."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _condense(text: str) -> str:
    """Reduce a result to its leading sentence, free of tables and symbols."""
    head = text.split(" | ")[0]
    head = re.split(r"(?<=[.!?])\s", head, maxsplit=1)[0]
    head = re.sub(r"^[^0-9A-Za-z]+", "", head).strip().rstrip(":").strip()
    if head and head[-1] not in ".!?":
        head += "."
    return head


def _fmt_time(value: datetime | None) -> str:
    """Format a datetime as a compact UTC string, or an em dash if missing."""
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_int(value: int) -> str:
    """Format an integer with thousands separators."""
    return f"{value:,}"
