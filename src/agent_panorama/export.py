"""Serialize a :class:`Report` to the JSON contract consumed by the frontend."""

from __future__ import annotations

from datetime import datetime

from .config import ReportConfig
from .models import AgentRollup, DecisionLogEntry, FeedItem, Report


def serialize_report(report: Report, config: ReportConfig) -> dict:
    """Convert a report into the ``feed.json`` dictionary contract.

    Args:
        report: The assembled report.
        config: Report configuration (reserved for future use).

    Returns:
        A JSON-serializable dict with ``generated_at``, ``time_range``,
        ``totals``, ``feed``, ``rollups``, and ``decision_log``.
    """
    start, end = report.time_range
    return {
        "generated_at": _iso(report.generated_at),
        "time_range": {"start": _iso(start), "end": _iso(end)},
        "totals": _totals(report),
        "feed": [_feed_item(item) for item in report.feed],
        "rollups": [_rollup(rollup) for rollup in report.rollups],
        "decision_log": [_decision(entry) for entry in report.decision_log],
    }


def _totals(report: Report) -> dict:
    """Serialize the report-level totals block."""
    return {
        "runs": report.total_runs,
        "steps": report.total_steps,
        "tokens": report.total_tokens,
        "cost_usd": report.total_cost_usd,
    }


def _feed_item(item: FeedItem) -> dict:
    """Serialize one feed item to the JSON contract."""
    return {
        "run_id": item.run_id,
        "agent_name": item.agent_name,
        "agent_key": item.agent_key,
        "action": item.action,
        "outcome": item.outcome.value,
        "timestamp": _iso(item.timestamp),
        "retry_count": item.retry_count,
        "anomaly_count": item.anomaly_count,
        "tokens": item.tokens,
        "cost_usd": item.cost_usd,
        "summary": item.summary,
        "facts": [[key, value] for key, value in item.facts],
        "anomalies": list(item.anomalies),
        "session_id": item.session_id,
        "actor": item.actor,
        "turn_count": item.turn_count,
        "run_ids": list(item.run_ids),
    }


def _rollup(rollup: AgentRollup) -> dict:
    """Serialize one per-agent rollup to the JSON contract."""
    return {
        "agent_name": rollup.agent_name,
        "agent_key": rollup.agent_key,
        "runs": rollup.runs,
        "actions": rollup.actions,
        "success_rate": rollup.success_rate,
        "escalation_rate": rollup.escalation_rate,
        "failure_rate": rollup.failure_rate,
        "retry_rate": rollup.retry_rate,
        "total_tokens": rollup.total_tokens,
        "total_cost_usd": rollup.total_cost_usd,
        "sessions": rollup.sessions,
    }


def _decision(entry: DecisionLogEntry) -> dict:
    """Serialize one decision-log entry to the JSON contract."""
    return {
        "timestamp": _iso(entry.timestamp),
        "agent_name": entry.agent_name,
        "action": entry.action,
        "parameters": entry.parameters,
        "outcome": entry.outcome,
    }


def _iso(value: datetime | None) -> str | None:
    """Format a datetime as an ISO-8601 UTC string, or None when absent."""
    return value.isoformat() if value is not None else None
