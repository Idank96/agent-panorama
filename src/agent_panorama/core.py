"""High-level orchestration: from a trace export to written report files."""

from __future__ import annotations

import json
from pathlib import Path

from . import parsers
from .analysis import build_report
from .config import ReportConfig, load_config
from .models import Report
from .render import render

_EXTENSIONS = {"md": ".md", "html": ".html"}


def generate_report(
    input_path: str | Path,
    output_dir: str | Path = "./report",
    formats: list[str] | None = None,
    input_type: str = "langfuse",
    config: ReportConfig | str | Path | None = None,
) -> Report:
    """Generate Agent Activity Report files from a trace export.

    Args:
        input_path: Path to a Langfuse/LangSmith JSON export.
        output_dir: Directory to write ``report.md`` / ``report.html`` into.
        formats: Output formats to write; defaults to ``["md", "html"]``.
        input_type: Trace format, ``"langfuse"`` or ``"langsmith"``.
        config: A :class:`ReportConfig`, a path to a YAML config, or None.

    Returns:
        The in-memory :class:`Report` that was rendered.
    """
    report_config = _resolve_config(config)
    report = build_report_from_file(input_path, input_type, report_config)
    _write_outputs(report, report_config, output_dir, formats or ["md", "html"])
    return report


def build_report_from_file(input_path: str | Path, input_type: str, config: ReportConfig) -> Report:
    """Parse a trace file and assemble an in-memory report (no files written).

    Args:
        input_path: Path to the JSON export.
        input_type: Trace format, ``"langfuse"`` or ``"langsmith"``.
        config: Report configuration.

    Returns:
        The assembled :class:`Report`.
    """
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    runs = parsers.parse(payload, input_type=input_type)
    return build_report(runs, config)


def _resolve_config(config: ReportConfig | str | Path | None) -> ReportConfig:
    """Coerce the ``config`` argument into a :class:`ReportConfig`."""
    if isinstance(config, ReportConfig):
        return config
    return load_config(config)


def _write_outputs(
    report: Report, config: ReportConfig, output_dir: str | Path, formats: list[str]
) -> list[Path]:
    """Render and write each requested format into the output directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in formats:
        path = out / f"report{_EXTENSIONS.get(fmt, '.' + fmt)}"
        path.write_text(render(report, config, fmt), encoding="utf-8")
        written.append(path)
    return written
