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


def _turn(
    run_id: str,
    when: datetime,
    output: str = "Answered the question.",
    *,
    session: str = "sess-1",
    user: str | None = "student-1",
    name: str = "tutor",
    errors: list[str] | None = None,
) -> AgentRun:
    return AgentRun(
        run_id=run_id,
        name=name,
        session_id=session,
        user_id=user,
        input_text=f"question {run_id}",
        output_text=output,
        start_time=when,
        error_messages=errors or [],
    )


def test_session_turns_aggregate_into_one_item() -> None:
    runs = [_turn("t1", _dt(20)), _turn("t2", _dt(21)), _turn("t3", _dt(22))]
    report = build_report(runs, ReportConfig())
    assert len(report.feed) == 1
    item = report.feed[0]
    assert item.turn_count == 3
    assert item.run_ids == ["t1", "t2", "t3"]
    assert item.session_id == "sess-1"
    assert item.actor == "student-1"
    assert item.run_id == "session:tutor:sess-1:student-1"


def test_sessionless_runs_stay_one_per_run() -> None:
    runs = [_run("a", "alpha", _dt(20)), _run("b", "alpha", _dt(21))]
    report = build_report(runs, ReportConfig())
    assert len(report.feed) == 2
    assert all(item.turn_count == 1 for item in report.feed)


def test_different_actors_split_into_separate_sessions() -> None:
    runs = [
        _turn("t1", _dt(20), user="student-1"),
        _turn("t2", _dt(21), user="student-2"),
    ]
    report = build_report(runs, ReportConfig())
    assert len(report.feed) == 2


def test_group_outcome_is_worst_of() -> None:
    runs = [
        _turn("ok", _dt(20)),
        _turn("bad", _dt(21), output="", errors=["boom"]),
    ]
    report = build_report(runs, ReportConfig())
    assert report.feed[0].outcome is Outcome.FAILURE


def test_group_facts_show_interactions_breakdown() -> None:
    runs = [
        _turn("ok1", _dt(20)),
        _turn("ok2", _dt(21)),
        _turn("bad", _dt(22), output="", errors=["boom"]),
    ]
    report = build_report(runs, ReportConfig())
    facts = dict(report.feed[0].facts)
    assert facts["Interactions"] == "3 · 1 failed · 2 ok"


def test_group_timestamp_is_latest_turn() -> None:
    runs = [_turn("t1", _dt(20)), _turn("t2", _dt(25))]
    report = build_report(runs, ReportConfig())
    assert report.feed[0].timestamp == _dt(25)


def test_group_action_is_deterministic_fallback() -> None:
    runs = [_turn("t1", _dt(20)), _turn("t2", _dt(21), output="Final answer here.")]
    report = build_report(runs, ReportConfig())
    assert report.feed[0].action == "Helped student-1: 2 interactions — Final answer here."


def test_rollup_counts_sessions_and_keeps_runs() -> None:
    runs = [
        _turn("t1", _dt(20)),
        _turn("t2", _dt(21)),
        _turn("u1", _dt(22), session="sess-2", user="student-2"),
        AgentRun(run_id="solo", name="tutor", output_text="ok", start_time=_dt(23)),
    ]
    report = build_report(runs, ReportConfig())
    rollup = report.rollups[0]
    assert rollup.runs == 4
    assert rollup.sessions == 2


def test_session_transcript_format_and_cap() -> None:
    from agent_panorama.analysis import session_transcript
    from agent_panorama.models import ToolCall

    turns = [
        AgentRun(
            run_id="t1",
            name="tutor",
            session_id="s",
            input_text="Why is the sky blue?",
            output_text="Explained scattering.",
            tool_calls=[ToolCall(name="web_search", arguments={})],
        ),
        AgentRun(run_id="t2", name="tutor", session_id="s", error_messages=["timeout"]),
    ]
    transcript = session_transcript(turns)
    lines = transcript.splitlines()
    assert lines[0] == "1. asked: Why is the sky blue? → web_search → result: Explained scattering."
    assert lines[1] == "2. asked: (none) → no tools → result: timeout"
    assert len(session_transcript(turns, max_chars=10)) == 10


def test_apply_session_summaries_overwrites_action(tmp_path, monkeypatch) -> None:
    from agent_panorama import core
    from agent_panorama.summarize import SummaryExchange

    runs = [_turn("t1", _dt(20)), _turn("t2", _dt(21))]
    report = build_report(runs, ReportConfig())

    def fake_exchange(transcript: str, model: str) -> SummaryExchange:
        return SummaryExchange(
            model, "sys", transcript, output="Helped the student with quiz prep."
        )

    import agent_panorama.summarize as summarize_module

    monkeypatch.setattr(summarize_module, "build_session_exchange", fake_exchange)
    core.apply_session_summaries(report, ReportConfig(), tmp_path)
    assert report.feed[0].action == "Helped the student with quiz prep."
    assert (tmp_path / "llm_calls.log").exists()


def test_apply_session_summaries_keeps_fallback_on_error(tmp_path, monkeypatch) -> None:
    from agent_panorama import core
    from agent_panorama.summarize import SummaryExchange

    runs = [_turn("t1", _dt(20)), _turn("t2", _dt(21))]
    report = build_report(runs, ReportConfig())
    deterministic = report.feed[0].action

    def failing_exchange(transcript: str, model: str) -> SummaryExchange:
        return SummaryExchange(model, "sys", transcript, error="no api key")

    import agent_panorama.summarize as summarize_module

    monkeypatch.setattr(summarize_module, "build_session_exchange", failing_exchange)
    core.apply_session_summaries(report, ReportConfig(), tmp_path)
    assert report.feed[0].action == deterministic


def test_single_turn_session_reads_like_a_normal_run() -> None:
    runs = [_turn("only", _dt(20), output="Reset the password.")]
    report = build_report(runs, ReportConfig())
    item = report.feed[0]
    assert item.turn_count == 1
    assert item.run_id == "session:tutor:sess-1:student-1"
    assert item.action == "Reset the password."
    assert "interactions" not in item.action
