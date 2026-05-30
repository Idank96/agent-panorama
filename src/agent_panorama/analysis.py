"""Derive business-level signals from normalized runs.

The parsers produce structurally accurate runs; this module layers on the
interpretation a non-engineer cares about: did it succeed, did it struggle
(retries / fallbacks), what consequential actions did it take, and what looks
unusual.
"""

from __future__ import annotations

from .config import ReportConfig
from .models import AgentRun, DecisionLogEntry, Outcome, Report, ToolCall


def build_report(runs: list[AgentRun], config: ReportConfig) -> Report:
    """Enrich runs with derived signals and assemble the final report.

    Args:
        runs: Normalized agent runs from a parser.
        config: Report configuration controlling naming and thresholds.

    Returns:
        A fully populated :class:`Report`.
    """
    for run in runs:
        _enrich_run(run, config)
    decision_log = _build_decision_log(runs, config)
    return Report(runs=runs, decision_log=decision_log)


def _enrich_run(run: AgentRun, config: ReportConfig) -> None:
    """Compute outcome, confidence signals, and anomalies for a single run."""
    run.retry_count = _count_retries(run)
    run.fallback_used = _detect_fallback(run)
    run.outcome = _determine_outcome(run, config)
    run.anomalies = _detect_anomalies(run, config)


def _count_retries(run: AgentRun) -> int:
    """Count recovery attempts: every failed tool or model call."""
    failed_tools = sum(1 for call in run.tool_calls if not call.succeeded)
    failed_llm = sum(1 for call in run.llm_calls if call.status != "success")
    return failed_tools + failed_llm


def _detect_fallback(run: AgentRun) -> bool:
    """Detect a fallback path used to recover from a failure.

    A fallback is inferred when a tool name mentions 'fallback', or when a tool
    failed and the same tool was later retried successfully (recovering via an
    alternate path). Using several models is intentionally NOT treated as a
    fallback: multi-agent graphs routinely use a different model per agent.
    """
    if any("fallback" in call.name.lower() for call in run.tool_calls):
        return True
    return _has_recovered_tool(run)


def _has_recovered_tool(run: AgentRun) -> bool:
    """Whether any tool failed and the same tool later succeeded."""
    failed = {call.name for call in run.tool_calls if not call.succeeded}
    succeeded = {call.name for call in run.tool_calls if call.succeeded}
    return bool(failed & succeeded)


def _determine_outcome(run: AgentRun, config: ReportConfig) -> Outcome:
    """Classify the run's final outcome in business terms."""
    if any(config.is_escalation(call.name) for call in run.tool_calls):
        return Outcome.ESCALATED
    if run.error_messages and not run.output_text:
        return Outcome.FAILURE
    if run.output_text:
        return Outcome.SUCCESS
    if run.error_messages:
        return Outcome.FAILURE
    return Outcome.UNKNOWN


def _detect_anomalies(run: AgentRun, config: ReportConfig) -> list[str]:
    """Produce human-readable anomaly notes for a run."""
    thresholds = config.anomaly_thresholds
    notes: list[str] = []
    _flag_retries(run, thresholds.max_retries, notes)
    _flag_latency(run, thresholds.max_latency_seconds, notes)
    _flag_tool_volume(run, thresholds.max_tool_calls, notes)
    _flag_errors(run, notes)
    return notes


def _flag_retries(run: AgentRun, limit: int, notes: list[str]) -> None:
    """Append a note when the run retried more than ``limit`` times."""
    if run.retry_count > limit:
        notes.append(f"High retry count: {run.retry_count} failed attempts before completing.")


def _flag_latency(run: AgentRun, limit_seconds: float, notes: list[str]) -> None:
    """Append a note when the run ran longer than ``limit_seconds``."""
    latency = run.latency_seconds
    if latency > limit_seconds:
        notes.append(f"Slow run: took {latency:.1f}s (threshold {limit_seconds:.0f}s).")


def _flag_tool_volume(run: AgentRun, limit: int, notes: list[str]) -> None:
    """Append a note when the run took an unusually high number of actions."""
    count = len(run.tool_calls)
    if count > limit:
        notes.append(f"Unusually high activity: {count} actions taken (threshold {limit}).")


def _flag_errors(run: AgentRun, notes: list[str]) -> None:
    """Append a note summarizing any errors encountered during the run."""
    if run.error_messages:
        first = run.error_messages[0]
        extra = f" (+{len(run.error_messages) - 1} more)" if len(run.error_messages) > 1 else ""
        notes.append(f"Errors encountered: {first}{extra}")
    if run.fallback_used:
        notes.append("Fell back to an alternate model or path to complete the task.")


def _build_decision_log(runs: list[AgentRun], config: ReportConfig) -> list[DecisionLogEntry]:
    """Collect consequential actions across all runs into a sorted table."""
    entries: list[DecisionLogEntry] = []
    for run in runs:
        for call in run.tool_calls:
            if config.is_consequential(call.name):
                entries.append(_to_log_entry(run, call, config))
    entries.sort(key=_log_sort_key)
    return entries


def _log_sort_key(entry: DecisionLogEntry) -> float:
    """Sort key placing timestamped entries first, in chronological order."""
    return entry.timestamp.timestamp() if entry.timestamp else float("inf")


def _to_log_entry(run: AgentRun, call: ToolCall, config: ReportConfig) -> DecisionLogEntry:
    """Build a single decision-log row from a tool call."""
    return DecisionLogEntry(
        timestamp=call.timestamp,
        agent_name=run.name,
        action=config.describe_tool(call.name),
        parameters=summarize_arguments(call.arguments),
        outcome="succeeded" if call.succeeded else f"failed: {call.error or 'error'}",
    )


def summarize_arguments(arguments: dict, max_items: int = 4, max_value: int = 60) -> str:
    """Summarize tool arguments as a plain-English ``key: value`` string.

    Args:
        arguments: The tool call arguments.
        max_items: Maximum number of arguments to include.
        max_value: Maximum length of each rendered value.

    Returns:
        A compact, human-readable description of the arguments.
    """
    if not arguments:
        return "—"
    items = list(arguments.items())[:max_items]
    parts = [_format_pair(key, value, max_value) for key, value in items]
    if len(arguments) > max_items:
        parts.append(f"+{len(arguments) - max_items} more")
    return ", ".join(parts)


def _format_pair(key: str, value: object, max_value: int) -> str:
    """Render one ``key: value`` argument pair, truncating long values."""
    label = str(key).replace("_", " ")
    rendered = " ".join(str(value).split())
    if len(rendered) > max_value:
        rendered = rendered[: max_value - 1].rstrip() + "…"
    return f"{label}: {rendered}"
