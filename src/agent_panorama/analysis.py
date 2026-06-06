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
    """Build the cross-agent activity feed, newest first.

    Runs sharing a ``(session_id, actor)`` pair aggregate into one item (the
    whole session is one "thing" the agent did); sessionless runs stay one
    item per run.
    """
    singles, groups = _partition_runs(runs)
    items = [_to_feed_item(run, config) for run in singles]
    items.extend(_to_group_item(key, turns, config) for key, turns in groups.items())
    items.sort(key=lambda item: item.timestamp.timestamp() if item.timestamp else float("-inf"))
    items.reverse()
    return items


def _partition_runs(runs: list[AgentRun]) -> tuple[list[AgentRun], dict[str, list[AgentRun]]]:
    """Split runs into sessionless singles and session groups (turns ordered)."""
    singles: list[AgentRun] = []
    groups: dict[str, list[AgentRun]] = {}
    for run in runs:
        key = session_group_key(run)
        if key is None:
            singles.append(run)
        else:
            groups.setdefault(key, []).append(run)
    for turns in groups.values():
        turns.sort(key=lambda r: r.start_time.timestamp() if r.start_time else float("inf"))
    return singles, groups


def session_group_key(run: AgentRun) -> str | None:
    """Stable feed identity for a run's session, or None when sessionless.

    The key doubles as the aggregated feed item's ``run_id``, so it must stay
    stable across rebuilds (frontend selection depends on it).
    """
    if not run.session_id:
        return None
    return f"session:{slugify(run.name)}:{run.session_id}:{run.user_id or ''}"


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


_OUTCOME_RANK = {Outcome.FAILURE: 3, Outcome.ESCALATED: 2, Outcome.UNKNOWN: 1, Outcome.SUCCESS: 0}

# Human labels for the per-outcome breakdown shown on aggregated feed items.
_OUTCOME_LABEL = {
    Outcome.SUCCESS: "ok",
    Outcome.FAILURE: "failed",
    Outcome.ESCALATED: "escalated",
    Outcome.UNKNOWN: "unknown",
}


def _to_group_item(key: str, turns: list[AgentRun], config: ReportConfig) -> FeedItem:
    """Aggregate one session's turns into a single feed item.

    The action text here is the deterministic fallback; the LLM session
    phrasing (when it succeeds) overwrites it post-build.
    """
    last = turns[-1]
    costs = [run.cost_usd for run in turns if run.cost_usd is not None]
    return FeedItem(
        run_id=key,
        agent_name=last.name,
        agent_key=slugify(last.name),
        action=_group_action_text(turns),
        outcome=_worst_outcome(turns),
        timestamp=max((r.start_time for r in turns if r.start_time), default=None),
        retry_count=sum(run.retry_count for run in turns),
        anomaly_count=len(_group_anomalies(turns)),
        tokens=sum(run.total_tokens for run in turns),
        cost_usd=sum(costs) if costs else None,
        summary=condense(last.output_text),
        facts=_group_facts(turns),
        anomalies=_group_anomalies(turns),
        session_id=last.session_id,
        actor=last.user_id,
        turn_count=len(turns),
        run_ids=[run.run_id for run in turns],
    )


def _group_action_text(turns: list[AgentRun]) -> str:
    """Deterministic one-line label for a whole session.

    A one-turn session reads like a normal run; the multi-turn phrasing kicks
    in once the conversation actually has several interactions.
    """
    if len(turns) == 1:
        return _action_text(turns[0])
    last = turns[-1]
    who = last.user_id or last.session_id or "user"
    result = condense(last.output_text) or condense(last.input_text)
    return f"Helped {who}: {len(turns)} interactions — {result}"


def _worst_outcome(turns: list[AgentRun]) -> Outcome:
    """Most severe outcome across the session's turns."""
    return max((run.outcome for run in turns), key=_OUTCOME_RANK.__getitem__)


def _group_anomalies(turns: list[AgentRun]) -> list[str]:
    """Order-preserving deduped union of every turn's anomalies."""
    seen: dict[str, None] = {}
    for run in turns:
        for note in run.anomalies:
            seen.setdefault(note, None)
    return list(seen)


def _group_facts(turns: list[AgentRun]) -> list[tuple[str, str]]:
    """Compact key/value facts for an aggregated session item."""
    facts = [
        ("Interactions", _interactions_breakdown(turns)),
        ("Retries", str(sum(run.retry_count for run in turns))),
        ("Model calls", str(sum(len(run.llm_calls) for run in turns))),
        ("Tokens", f"{sum(run.total_tokens for run in turns):,}"),
    ]
    costs = [run.cost_usd for run in turns if run.cost_usd is not None]
    if costs:
        facts.append(("Est. cost", f"${sum(costs):.4f}"))
    return facts


def _interactions_breakdown(turns: list[AgentRun]) -> str:
    """Render '4 · 3 ok · 1 failed' style per-outcome counts."""
    counts: dict[Outcome, int] = {}
    for run in turns:
        counts[run.outcome] = counts.get(run.outcome, 0) + 1
    parts = [
        f"{counts[outcome]} {_OUTCOME_LABEL[outcome]}"
        for outcome in sorted(counts, key=_OUTCOME_RANK.__getitem__, reverse=True)
    ]
    return " · ".join([str(len(turns)), *parts])


def session_transcript(turns: list[AgentRun], max_chars: int = 1500) -> str:
    """Concatenate a session's turns into a compact numbered transcript.

    The transcript is what the LLM session phrasing receives: one line per
    turn — what was asked, which tools ran, what came back.

    Args:
        turns: The session's runs, ordered by start time.
        max_chars: Hard cap on the rendered transcript length.

    Returns:
        A newline-joined transcript, truncated to ``max_chars``.
    """
    lines = [_turn_line(index, run) for index, run in enumerate(turns, 1)]
    return "\n".join(lines)[:max_chars]


def _turn_line(index: int, run: AgentRun) -> str:
    """Render one transcript line for a single turn."""
    tools = ", ".join(call.name for call in run.tool_calls) or "no tools"
    asked = condense(run.input_text) or "(none)"
    result = condense(run.output_text) or (run.error_messages[0] if run.error_messages else "")
    return f"{index}. asked: {asked} → {tools} → result: {result or '(none)'}"


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
    """Compute a single agent's rollup metrics and outcome rates.

    Rates stay per-run (per turn) so they remain statistically honest;
    ``sessions`` counts the distinct conversations those runs belong to.
    """
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
        sessions=len({run.session_id for run in group if run.session_id}),
    )


def _rate(group: list[AgentRun], total: int, outcome: Outcome) -> float:
    """Share of runs in ``group`` with the given outcome."""
    return sum(1 for run in group if run.outcome == outcome) / total
