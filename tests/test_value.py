"""Tests for the value layer's pipeline integration: config, batch, rollups, export."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

import pytest  # noqa: E402

from agent_panorama import core  # noqa: E402
from agent_panorama.analysis import (  # noqa: E402
    VALUABLE_SCORE_THRESHOLD,
    apply_value_rollups,
    build_report,
    value_totals,
)
from agent_panorama.config import ReportConfig, ValueLayerConfig, _config_from_dict  # noqa: E402
from agent_panorama.export import serialize_report  # noqa: E402
from agent_panorama.layers.value import ValueContext  # noqa: E402
from agent_panorama.layers.value.judge import ValueJudgmentExchange  # noqa: E402
from agent_panorama.models import AgentRun, ValueJudgment  # noqa: E402

_BASE = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _dt(minute: int) -> datetime:
    return _BASE + timedelta(minutes=minute)


def _run(run_id: str, minute: int, session: str | None = None, name: str = "tutor") -> AgentRun:
    return AgentRun(
        run_id=run_id,
        name=name,
        session_id=session,
        user_id="student-1" if session else None,
        input_text=f"question {run_id}",
        output_text=f"answer {run_id}",
        start_time=_dt(minute),
        end_time=_dt(minute + 1),
    )


def _judgment(score: int = 8) -> ValueJudgment:
    return ValueJudgment(
        overall_score=score,
        goal_completion=score,
        response_quality=score,
        efficiency=score,
        outcome="student understood the topic",
        rationale="cited evidence",
    )


def _value_config(**overrides) -> ValueLayerConfig:
    config = ValueLayerConfig(default=ValueContext(domain="education"))
    for key, val in overrides.items():
        setattr(config, key, val)
    return config


def _fake_judge(score: int = 8, calls: list | None = None):
    def fake(turns, context=None, model="stub", chat_model=None) -> ValueJudgmentExchange:
        if calls is not None:
            calls.append((tuple(run.run_id for run in turns), context))
        return ValueJudgmentExchange(model, "sys", "transcript", judgment=_judgment(score))

    return fake


def test_value_yaml_block_parses_contexts_and_defaults() -> None:
    config = _config_from_dict(
        {
            "value": {
                "judge_model": "openai:gpt-5-nano",
                "max_judgments": 5,
                "include_single_runs": False,
                "default": {"domain": "support", "success_criteria": ["resolved"]},
                "contexts": {"tutor": {"user_goal": "student understands"}},
            }
        }
    )
    assert config.value is not None
    assert config.value.judge_model == "openai:gpt-5-nano"
    assert config.value.max_judgments == 5
    assert config.value.include_single_runs is False
    resolved = config.value.context_for("tutor")
    assert resolved is not None
    assert resolved.user_goal == "student understands"
    assert resolved.domain == "support"
    assert config.value.context_for("other-agent").domain == "support"


def test_no_value_block_means_no_value_config() -> None:
    assert _config_from_dict({}).value is None
    assert ReportConfig().value is None


def test_apply_value_judgments_noop_without_config(tmp_path, monkeypatch) -> None:
    import agent_panorama.layers.value as value_layer

    calls: list = []
    monkeypatch.setattr(value_layer, "judge_session", _fake_judge(calls=calls))
    report = build_report([_run("r1", 0)], ReportConfig())
    core.apply_value_judgments(report, ReportConfig(), tmp_path)
    assert calls == []
    assert report.feed[0].value is None
    assert not (tmp_path / "llm_calls.log").exists()


def test_apply_value_judgments_attaches_judgment_and_logs(tmp_path, monkeypatch) -> None:
    import agent_panorama.layers.value as value_layer

    calls: list = []
    monkeypatch.setattr(value_layer, "judge_session", _fake_judge(calls=calls))
    config = ReportConfig(value=_value_config())
    runs = [_run("t1", 0, session="sess-1"), _run("t2", 1, session="sess-1"), _run("solo", 2)]
    report = build_report(runs, config)
    core.apply_value_judgments(report, config, tmp_path)

    assert all(item.value is not None for item in report.feed)
    session_call = next(call for call in calls if len(call[0]) == 2)
    assert session_call[0] == ("t1", "t2")
    assert session_call[1].domain == "education"
    assert (tmp_path / "llm_calls.log").exists()
    assert "overall_score" in (tmp_path / "llm_calls.log").read_text(encoding="utf-8")


def test_apply_value_judgments_respects_cap_and_single_run_opt_out(tmp_path, monkeypatch) -> None:
    import agent_panorama.layers.value as value_layer

    calls: list = []
    monkeypatch.setattr(value_layer, "judge_session", _fake_judge(calls=calls))
    config = ReportConfig(value=_value_config(include_single_runs=False, max_judgments=1))
    runs = [
        _run("t1", 0, session="sess-1"),
        _run("solo-a", 1),
        _run("t2", 2, session="sess-1"),
        _run("u1", 3, session="sess-2"),
        _run("u2", 4, session="sess-2"),
    ]
    report = build_report(runs, config)
    core.apply_value_judgments(report, config, tmp_path)

    assert len(calls) == 1
    judged = [item for item in report.feed if item.value is not None]
    assert len(judged) == 1
    assert judged[0].turn_count == 2
    solo = next(item for item in report.feed if item.run_id == "solo-a")
    assert solo.value is None


def test_failed_judgment_leaves_item_unjudged(tmp_path, monkeypatch) -> None:
    import agent_panorama.layers.value as value_layer

    def failing(turns, context=None, model="stub", chat_model=None) -> ValueJudgmentExchange:
        return ValueJudgmentExchange(model, "sys", "transcript", error="no api key")

    monkeypatch.setattr(value_layer, "judge_session", failing)
    config = ReportConfig(value=_value_config())
    report = build_report([_run("r1", 0)], config)
    core.apply_value_judgments(report, config, tmp_path)
    assert report.feed[0].value is None
    assert "no api key" in (tmp_path / "llm_calls.log").read_text(encoding="utf-8")


def test_apply_value_rollups_computes_rates() -> None:
    report = build_report([_run("r1", 0), _run("r2", 1), _run("r3", 2)], ReportConfig())
    report.feed[0].value = _judgment(score=9)
    report.feed[1].value = _judgment(score=VALUABLE_SCORE_THRESHOLD - 3)
    report.runs[0].cost_usd = 0.10
    report.rollups[0].total_cost_usd = 0.10
    apply_value_rollups(report)

    rollup = report.rollups[0]
    assert rollup.judged == 2
    assert rollup.avg_value_score == pytest.approx((9 + VALUABLE_SCORE_THRESHOLD - 3) / 2)
    assert rollup.valuable_rate == pytest.approx(0.5)
    assert rollup.cost_per_valuable_usd == pytest.approx(0.10)

    totals = value_totals(report)
    assert totals is not None
    assert totals["judged"] == 2
    assert totals["cost_per_valuable_usd"] == pytest.approx(0.10)


def test_unjudged_report_keeps_value_fields_absent() -> None:
    config = ReportConfig()
    report = build_report([_run("r1", 0)], config)
    apply_value_rollups(report)
    assert value_totals(report) is None
    assert report.rollups[0].judged == 0
    assert report.rollups[0].avg_value_score is None

    data = serialize_report(report, config)
    assert data["totals"]["value"] is None
    assert data["feed"][0]["value"] is None
    assert data["rollups"][0]["avg_value_score"] is None


def test_serialized_judgment_round_trips() -> None:
    config = ReportConfig()
    report = build_report([_run("r1", 0)], config)
    report.feed[0].value = _judgment(score=7)
    apply_value_rollups(report)

    data = serialize_report(report, config)
    judged = data["feed"][0]["value"]
    assert judged["overall_score"] == 7
    assert judged["outcome"] == "student understood the topic"
    assert data["rollups"][0]["judged"] == 1
    assert data["totals"]["value"]["valuable_rate"] == 1.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
