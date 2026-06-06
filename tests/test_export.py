"""Tests for the JSON export contract consumed by the frontend."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402

import pytest  # noqa: E402

from agent_panorama import parsers  # noqa: E402
from agent_panorama.analysis import build_report  # noqa: E402
from agent_panorama.config import ReportConfig  # noqa: E402
from agent_panorama.export import serialize_report  # noqa: E402

_LANGFUSE = _bootstrap.EXAMPLES / "langfuse_traces.json"
_OUTCOME_STRINGS = {"success", "failure", "human-escalated", "unknown"}
_TOP_LEVEL = {"generated_at", "time_range", "totals", "feed", "rollups", "decision_log"}


def _serialized() -> dict:
    payload = json.loads(_LANGFUSE.read_text("utf-8"))
    runs = parsers.parse(payload, input_type="langfuse")
    report = build_report(runs, ReportConfig())
    return serialize_report(report, ReportConfig())


def test_top_level_keys_present() -> None:
    data = _serialized()
    assert set(data) == _TOP_LEVEL


def test_totals_block_shape() -> None:
    totals = _serialized()["totals"]
    assert set(totals) == {"runs", "steps", "tokens", "cost_usd"}
    assert totals["cost_usd"] is None


def test_json_round_trips() -> None:
    data = _serialized()
    restored = json.loads(json.dumps(data, indent=2))
    assert restored == data


def test_feed_outcomes_are_valid() -> None:
    for item in _serialized()["feed"]:
        assert item["outcome"] in _OUTCOME_STRINGS
        assert isinstance(item["facts"], list)


def test_cost_serialized_when_priced() -> None:
    payload = json.loads(_LANGFUSE.read_text("utf-8"))
    runs = parsers.parse(payload, input_type="langfuse")
    config = ReportConfig(model_prices={"gpt-4o": {"input": 2.5, "output": 10.0}})
    data = serialize_report(build_report(runs, config), config)
    assert data["totals"]["cost_usd"] is not None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


def test_feed_items_expose_session_fields() -> None:
    for item in _serialized()["feed"]:
        assert "session_id" in item
        assert "actor" in item
        assert "turn_count" in item
        assert "run_ids" in item


def test_rollups_expose_sessions_count() -> None:
    for rollup in _serialized()["rollups"]:
        assert "sessions" in rollup
        assert isinstance(rollup["sessions"], int)


def test_aggregated_session_serializes_group_fields() -> None:
    from agent_panorama.models import AgentRun

    runs = [
        AgentRun(
            run_id=f"t{i}",
            name="tutor",
            session_id="sess-1",
            user_id="student-1",
            output_text="answered",
        )
        for i in (1, 2)
    ]
    data = serialize_report(build_report(runs, ReportConfig()), ReportConfig())
    item = data["feed"][0]
    assert item["turn_count"] == 2
    assert item["session_id"] == "sess-1"
    assert item["actor"] == "student-1"
    assert item["run_ids"] == ["t1", "t2"]
    assert data["rollups"][0]["sessions"] == 1
