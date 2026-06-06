"""High-level orchestration: from a trace export to written report files."""

from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from . import parsers
from .analysis import build_report, rebuild_feed
from .config import ReportConfig, load_config
from .export import serialize_report
from .models import AgentRun, Report
from .render import render

if TYPE_CHECKING:
    from .summarize import SummaryExchange

_EXTENSIONS = {"md": ".md", "html": ".html", "json": ".json"}


def generate_report(
    inputs: str | Path | list[str | Path] | None = None,
    output_dir: str | Path = "./report",
    formats: list[str] | None = None,
    input_type: str = "langfuse",
    config: ReportConfig | str | Path | None = None,
    detail: str | None = None,
    summarize: bool = False,
    *,
    input_path: str | Path | None = None,
    session: str | None = None,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
) -> Report:
    """Generate Agent Activity Report files from one or more trace exports.

    Args:
        inputs: A path, glob, directory, or list of any of those. Back-compatible
            with a single path passed positionally.
        output_dir: Directory to write report files into.
        formats: Output formats to write; defaults to ``["md", "html"]``.
        input_type: Trace format, ``"langfuse"`` or ``"langsmith"``.
        config: A :class:`ReportConfig`, a path to a YAML config, or None.
        detail: Narrative detail level; when set, overrides ``config``.
        summarize: When True, phrase each run's minimal result via a cheap LLM.
        input_path: Deprecated alias for ``inputs`` (kept for back-compat).
        session: Keep only runs matching this session id.
        since: Keep only runs starting at or after this ISO date/datetime.
        until: Keep only runs starting at or before this ISO date/datetime.

    Returns:
        The in-memory :class:`Report` that was rendered.
    """
    report_config = _resolve_config(config)
    if detail is not None:
        report_config.detail = detail
    source = inputs if inputs is not None else input_path
    report = build_report_from_inputs(
        source, input_type, report_config, session=session, since=since, until=until
    )
    if summarize:
        _summarize_results(report, report_config, Path(output_dir))
        rebuild_feed(report, report_config)
    apply_session_summaries(report, report_config, Path(output_dir))
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


def apply_session_summaries(report: Report, config: ReportConfig, output_dir: Path) -> None:
    """Phrase each aggregated session feed item via the LLM layer, in place.

    Runs after the feed is final (never followed by ``rebuild_feed``, which
    would clobber the phrasing). Degrades gracefully: on any failure the item
    keeps its deterministic action line. Every exchange is appended to
    ``<output_dir>/llm_calls.log``.

    Args:
        report: The assembled report whose feed may contain session aggregates.
        config: Report configuration (supplies ``summarize_model``).
        output_dir: Directory receiving the LLM audit log.
    """
    from .analysis import session_transcript
    from .summarize import build_session_exchange

    runs_by_id = {run.run_id: run for run in report.runs}
    exchanges = []
    for item in report.feed:
        if item.turn_count <= 1:
            continue
        turns = [runs_by_id[run_id] for run_id in item.run_ids if run_id in runs_by_id]
        exchange = build_session_exchange(session_transcript(turns), config.summarize_model)
        if exchange.output:
            item.action = exchange.output
        exchanges.append((item.run_id, item.agent_name, exchange))
    if exchanges:
        _write_llm_log(output_dir / "llm_calls.log", exchanges)


def _write_llm_log(path: Path, exchanges: list) -> None:
    """Write a human-readable audit log of every LLM summarization call."""
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    blocks = [_format_llm_block(stamp, run_id, name, ex) for run_id, name, ex in exchanges]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("".join(blocks))


def _format_llm_block(stamp: str, run_id: str, name: str, exchange: SummaryExchange) -> str:
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


def build_report_from_inputs(
    inputs: str | Path | list[str | Path] | None,
    input_type: str,
    config: ReportConfig,
    *,
    session: str | None = None,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
) -> Report:
    """Load runs from one or more inputs, filter them, and build the report.

    Args:
        inputs: A path, glob, directory, or list of any of those.
        input_type: Trace format, ``"langfuse"`` or ``"langsmith"``.
        config: Report configuration.
        session: Keep only runs matching this session id.
        since: Lower bound (inclusive) on each run's start time.
        until: Upper bound (inclusive) on each run's start time.

    Returns:
        The assembled :class:`Report`.
    """
    runs = load_runs(inputs, input_type, session=session, since=since, until=until)
    return build_report(runs, config)


def load_runs(
    inputs: str | Path | list[str | Path] | None,
    input_type: str = "langfuse",
    *,
    session: str | None = None,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
) -> list[AgentRun]:
    """Load and filter runs from any combination of files, globs, and dirs.

    Args:
        inputs: A path, glob, directory, or list of any of those.
        input_type: Trace format, ``"langfuse"`` or ``"langsmith"``.
        session: Keep only runs matching this session id.
        since: Lower bound (inclusive) on each run's start time.
        until: Upper bound (inclusive) on each run's start time.

    Returns:
        The concatenated, filtered list of runs.

    Raises:
        ValueError: If ``inputs`` resolves to zero existing JSON files.
    """
    files = _resolve_files(inputs)
    if not files:
        raise ValueError(f"No JSON files matched the given input(s): {inputs!r}")
    runs: list[AgentRun] = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        runs.extend(parsers.parse(payload, input_type=input_type))
    return _filter_runs(runs, session, since, until)


def _resolve_files(inputs: str | Path | list[str | Path] | None) -> list[Path]:
    """Expand inputs (paths/globs/dirs/lists) into a deduped, sorted file list."""
    if inputs is None:
        return []
    items = inputs if isinstance(inputs, list) else [inputs]
    seen: dict[str, Path] = {}
    for item in items:
        for path in _expand_one(item):
            seen[str(path.resolve())] = path
    return sorted(seen.values(), key=lambda p: str(p))


def _expand_one(item: str | Path) -> list[Path]:
    """Expand a single input into its matching JSON file paths."""
    path = Path(item)
    if path.is_dir():
        return sorted(path.glob("*.json"))
    matches = glob.glob(str(item))
    if matches:
        return [Path(m) for m in matches if Path(m).is_file()]
    return [path] if path.is_file() else []


def _filter_runs(
    runs: list[AgentRun],
    session: str | None,
    since: str | datetime | None,
    until: str | datetime | None,
) -> list[AgentRun]:
    """Apply session and time-window filters to a list of runs."""
    lower = _coerce_dt(since)
    upper = _coerce_dt(until)
    result = runs
    if session is not None:
        result = [run for run in result if _matches_session(run, session)]
    if lower is not None or upper is not None:
        result = [run for run in result if _within_window(run, lower, upper)]
    return result


def _matches_session(run: AgentRun, session: str) -> bool:
    """Whether a run belongs to the given session.

    Prefers the run's real ``session_id``; falls back to the legacy best-effort
    run-id match for traces that carry no session.
    """
    if run.session_id is not None:
        return run.session_id == session
    return run.run_id == session or session in run.run_id


def _within_window(run: AgentRun, lower: datetime | None, upper: datetime | None) -> bool:
    """Whether a run's start time falls within ``[lower, upper]``."""
    start = run.start_time
    if start is None:
        return False
    if lower is not None and start < lower:
        return False
    return not (upper is not None and start > upper)


def _coerce_dt(value: str | datetime | None) -> datetime | None:
    """Coerce an ISO date/datetime string (or datetime) to tz-aware UTC."""
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
        path.write_text(_render_format(report, config, fmt), encoding="utf-8")
        written.append(path)
    return written


def _render_format(report: Report, config: ReportConfig, fmt: str) -> str:
    """Render a report to a single output format's text content."""
    if fmt == "json":
        return json.dumps(serialize_report(report, config), indent=2)
    return render(report, config, fmt)
