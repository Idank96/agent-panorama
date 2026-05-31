"""Derive business-level signals from normalized runs.

The parsers produce structurally accurate runs; this module layers on the
interpretation a non-engineer cares about: did it succeed, did it struggle
(retries / fallbacks), what consequential actions did it take, and what looks
unusual.
"""

from __future__ import annotations

from .config import ReportConfig
from .models import AgentRollup, AgentRun, DecisionLogEntry, FeedItem, Outcome, Report, ToolCall
from .text import condense, slugify


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
    return Report(
        runs=runs,
        decision_log=_build_decision_log(runs, config),
        feed=_build_feed(runs, config),
        rollups=_build_rollups(runs, config),
    )


def rebuild_feed(report: Report, config: ReportConfig) -> None:
    """Recompute the activity feed from current run state, in place.

    Call this after mutating runs post-build (e.g. LLM summarization sets
    ``result_summary``) so the feed's action text reflects the new values.

    Args:
        report: The report whose feed should be refreshed.
        config: Report configuration controlling naming.
    """
    report.feed = _build_feed(report.runs, config)


def _enrich_run(run: AgentRun, config: ReportConfig) -> None:
    """Compute outcome, confidence signals, and anomalies for a single run."""
    run.retry_count = _count_retries(run)
    run.fallback_used = _detect_fallback(run)
    run.outcome = _determine_outcome(run, config)
    run.anomalies = _detect_anomalies(run, config)
    run.cost_usd = _estimate_cost(run, config)


def _estimate_cost(run: AgentRun, config: ReportConfig) -> float | None:
    """Estimate a run's USD cost from priced model calls.

    Sums input/output token cost across every model call whose model matches a
    configured price. Returns None when no call matched a price (so cost stays
    absent rather than misleadingly zero).
    """
    total = 0.0
    matched = False
    for call in run.llm_calls:
        price = config.price_for(call.model)
        if price is None:
            continue
        matched = True
        total += call.input_tokens / 1e6 * price.get("input", 0.0)
        total += call.output_tokens / 1e6 * price.get("output", 0.0)
    return total if matched else None


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


def _build_feed(runs: list[AgentRun], config: ReportConfig) -> list[FeedItem]:
    """Build one cross-agent feed item per run, newest first."""
    items = [_to_feed_item(run, config) for run in runs]
    items.sort(key=lambda item: item.timestamp.timestamp() if item.timestamp else float("-inf"))
    items.reverse()
    return items


def _to_feed_item(run: AgentRun, config: ReportConfig) -> FeedItem:
    """Build a single feed item from an enriched run."""
    return FeedItem(
        run_id=run.run_id,
        agent_name=run.name,
        agent_key=slugify(run.name),
        action=_action_text(run),
        outcome=run.outcome,
        timestamp=run.start_time,
        retry_count=run.retry_count,
        anomaly_count=len(run.anomalies),
        tokens=run.total_tokens,
        cost_usd=run.cost_usd,
        summary=condense(run.output_text),
        facts=_feed_facts(run),
        anomalies=list(run.anomalies),
    )


def _action_text(run: AgentRun) -> str:
    """Pick the most descriptive one-line action label for a run."""
    return run.result_summary or condense(run.output_text) or condense(run.input_text)


def _feed_facts(run: AgentRun) -> list[tuple[str, str]]:
    """Build the compact key/value facts shown on a feed item."""
    facts = [
        ("Steps", str(run.action_count)),
        ("Retries", str(run.retry_count)),
        ("Model calls", str(len(run.llm_calls))),
        ("Tokens", f"{run.total_tokens:,}"),
    ]
    if run.cost_usd is not None:
        facts.append(("Est. cost", f"${run.cost_usd:.4f}"))
    return facts


def _build_rollups(runs: list[AgentRun], config: ReportConfig) -> list[AgentRollup]:
    """Aggregate runs into per-agent rollups, grouped by agent key."""
    groups: dict[str, list[AgentRun]] = {}
    for run in runs:
        groups.setdefault(slugify(run.name), []).append(run)
    return [_to_rollup(key, group) for key, group in groups.items()]


def _to_rollup(agent_key: str, group: list[AgentRun]) -> AgentRollup:
    """Compute a single agent's rollup metrics and outcome rates."""
    total = len(group)
    costs = [run.cost_usd for run in group if run.cost_usd is not None]
    return AgentRollup(
        agent_name=group[0].name,
        agent_key=agent_key,
        runs=total,
        actions=sum(len(run.tool_calls) for run in group),
        success_rate=_rate(group, total, Outcome.SUCCESS),
        escalation_rate=_rate(group, total, Outcome.ESCALATED),
        failure_rate=_rate(group, total, Outcome.FAILURE),
        retry_rate=sum(1 for run in group if run.retry_count > 0) / total,
        total_tokens=sum(run.total_tokens for run in group),
        total_cost_usd=sum(costs) if costs else None,
    )


def _rate(group: list[AgentRun], total: int, outcome: Outcome) -> float:
    """Share of runs in ``group`` with the given outcome."""
    return sum(1 for run in group if run.outcome == outcome) / total
