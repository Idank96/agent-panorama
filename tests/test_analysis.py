"""Tests for derived signals: outcome, retries, fallback, anomalies, decision log."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402

import pytest  # noqa: E402

from agent_panorama import parsers  # noqa: E402
from agent_panorama.analysis import build_report, summarize_arguments  # noqa: E402
from agent_panorama.config import ReportConfig  # noqa: E402
from agent_panorama.models import Outcome  # noqa: E402


def _report(config: ReportConfig | None = None):
    payload = json.loads((_bootstrap.EXAMPLES / "langfuse_traces.json").read_text("utf-8"))
    runs = parsers.parse(payload, input_type="langfuse")
    return build_report(runs, config or ReportConfig())


def test_success_outcome() -> None:
    report = _report()
    research = next(r for r in report.runs if r.name == "research-assistant")
    assert research.outcome is Outcome.SUCCESS


def test_escalation_outcome() -> None:
    report = _report()
    scheduling = next(r for r in report.runs if r.name == "scheduling-assistant")
    assert scheduling.outcome is Outcome.ESCALATED


def test_fallback_and_retry_detected() -> None:
    report = _report()
    weather = next(r for r in report.runs if r.name == "weather-assistant")
    assert weather.retry_count == 1
    assert weather.fallback_used is True
    assert any("Fell back" in note for note in weather.anomalies)


def test_consequential_filter_limits_decision_log() -> None:
    config = ReportConfig(consequential_tools=["send_email", "human_handoff"])
    report = _report(config)
    # Only the two consequential tools (humanized) should appear.
    actions = {entry.action for entry in report.decision_log}
    assert actions == {"Send email", "Human handoff"}
    assert len(report.decision_log) == 2


def test_tool_descriptions_applied_in_log() -> None:
    config = ReportConfig(
        tool_descriptions={"send_email": "Sent an email"},
        consequential_tools=["send_email"],
    )
    report = _report(config)
    assert report.decision_log[0].action == "Sent an email"


def test_summarize_arguments_plain_english() -> None:
    text = summarize_arguments({"city": "Paris", "provider": "backup"})
    assert "city: Paris" in text
    assert "provider: backup" in text


def test_summarize_arguments_truncates_items() -> None:
    args = {f"k{i}": i for i in range(10)}
    text = summarize_arguments(args, max_items=3)
    assert "more" in text


def test_report_totals() -> None:
    report = _report()
    assert report.total_runs == 3
    assert report.total_actions == sum(len(r.tool_calls) for r in report.runs)
    assert report.total_tokens > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
