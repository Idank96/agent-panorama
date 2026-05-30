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
    detail: str | None = None,
    summarize: bool = False,
) -> Report:
    """Generate Agent Activity Report files from a trace export.

    Args:
        input_path: Path to a Langfuse/LangSmith JSON export.
        output_dir: Directory to write ``report.md`` / ``report.html`` into.
        formats: Output formats to write; defaults to ``["md", "html"]``.
        input_type: Trace format, ``"langfuse"`` or ``"langsmith"``.
        config: A :class:`ReportConfig`, a path to a YAML config, or None.
        detail: Narrative detail level (``"minimal"``/``"standard"``/``"richer"``);
            when set, overrides the value from ``config``.
        summarize: When True, phrase each run's minimal result via a cheap LLM
            (see :mod:`agent_panorama.summarize`). Opt-in; off by default.

    Returns:
        The in-memory :class:`Report` that was rendered.
    """
    report_config = _resolve_config(config)
    if detail is not None:
        report_config.detail = detail
    report = build_report_from_file(input_path, input_type, report_config)
    if summarize:
        _summarize_results(report, report_config, Path(output_dir))
    _write_outputs(report, report_config, output_dir, formats or ["md", "html"])
    return report


def _summarize_results(report: Report, config: ReportConfig, output_dir: Path) -> None:
    """Attach an LLM one-line action summary to each run, logging every call.

    Only runs when it would be shown (minimal detail), so no model is called
    unnecessarily. Every exchange (system prompt, input sent, output/error) is
    appended to ``<output_dir>/llm_calls.log`` for auditing.
    """
    if config.detail != "minimal":
        return
    from .summarize import build_exchange

    exchanges = []
    for run in report.runs:
        exchange = build_exchange(run.output_text, config.summarize_model)
        if exchange.output:
            run.result_summary = exchange.output
        exchanges.append((run.run_id, run.name, exchange))
    _write_llm_log(output_dir / "llm_calls.log", exchanges)


def _write_llm_log(path: Path, exchanges: list) -> None:
    """Write a human-readable audit log of every LLM summarization call."""
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    blocks = [_format_llm_block(stamp, run_id, name, ex) for run_id, name, ex in exchanges]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("".join(blocks))


def _format_llm_block(stamp: str, run_id: str, name: str, exchange) -> str:
    """Render one LLM exchange as a delimited, readable log block."""
    rule = "=" * 72
    output = (
        exchange.output if exchange.output is not None else f"(no output) ERROR: {exchange.error}"
    )
    return (
        f"{rule}\n"
        f"{stamp} | run {run_id} ({name}) | model: {exchange.model}\n"
        f"{rule}\n"
        f"----- SYSTEM PROMPT -----\n{exchange.system_prompt}\n\n"
        f"----- INPUT SENT ({len(exchange.input_text)} chars) -----\n{exchange.input_text}\n\n"
        f"----- OUTPUT -----\n{output}\n\n"
    )


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
