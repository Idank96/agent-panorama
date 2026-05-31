"""Tests for the cross-agent feed and per-agent rollups."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

import pytest  # noqa: E402

from agent_panorama.analysis import build_report, rebuild_feed  # noqa: E402
from agent_panorama.config import ReportConfig  # noqa: E402
from agent_panorama.models import AgentRun, Outcome  # noqa: E402

_OUTCOME_STRINGS = {"success", "failure", "human-escalated", "unknown"}


def _run(
    run_id: str, name: str, when: datetime | None, output: str = "Done the thing."
) -> AgentRun:
    return AgentRun(run_id=run_id, name=name, output_text=output, start_time=when)


def _dt(day: int) -> datetime:
    return datetime(2026, 5, day, 9, 0, 0, tzinfo=timezone.utc)


def test_feed_is_newest_first_with_none_last() -> None:
    runs = [
        _run("a", "alpha", _dt(20)),
        _run("b", "beta", _dt(25)),
        _run("c", "gamma", None),
    ]
    report = build_report(runs, ReportConfig())
    assert [item.run_id for item in report.feed] == ["b", "a", "c"]


def test_feed_action_text_non_empty() -> None:
    report = build_report([_run("a", "alpha", _dt(20))], ReportConfig())
    assert report.feed[0].action
    assert report.feed[0].outcome.value in _OUTCOME_STRINGS


def test_feed_outcomes_are_valid_strings() -> None:
    runs = [_run("a", "alpha", _dt(20))]
    report = build_report(runs, ReportConfig())
    for item in report.feed:
        assert item.outcome in Outcome
        assert item.outcome.value in _OUTCOME_STRINGS


def test_rollup_rates() -> None:
    runs = [
        _run("a1", "alpha", _dt(20), output="ok"),
        _run("a2", "alpha", _dt(21), output=""),
        _run("b1", "beta", _dt(22), output="ok"),
    ]
    runs[1].error_messages = ["boom"]
    report = build_report(runs, ReportConfig())
    by_key = {rollup.agent_key: rollup for rollup in report.rollups}
    alpha = by_key["alpha"]
    assert alpha.runs == 2
    assert alpha.success_rate == 0.5
    assert alpha.failure_rate == 0.5
    assert by_key["beta"].success_rate == 1.0


def test_rebuild_feed_picks_up_result_summary() -> None:
    report = build_report(
        [_run("a", "alpha", _dt(20), output="A long raw answer.")], ReportConfig()
    )
    report.runs[0].result_summary = "Phrased the answer crisply."
    rebuild_feed(report, ReportConfig())
    assert report.feed[0].action == "Phrased the answer crisply."


def test_retry_rate_counts_runs_with_retries() -> None:
    run = _run("a", "alpha", _dt(20))
    run.retry_count = 0
    other = _run("b", "alpha", _dt(21))
    report = build_report([run, other], ReportConfig())
    assert report.rollups[0].retry_rate == 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
