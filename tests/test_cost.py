"""Tests for opt-in USD cost estimation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

import pytest  # noqa: E402

from agent_panorama.analysis import build_report  # noqa: E402
from agent_panorama.config import ReportConfig  # noqa: E402
from agent_panorama.models import AgentRun, LLMCall  # noqa: E402

_PRICES = {"gpt-4o": {"input": 2.50, "output": 10.00}}


def _run_with_call(model: str) -> AgentRun:
    call = LLMCall(name="gen", model=model, input_tokens=1_000_000, output_tokens=1_000_000)
    return AgentRun(run_id="r", name="agent", output_text="ok", llm_calls=[call])


def test_cost_computed_from_prices() -> None:
    report = build_report([_run_with_call("gpt-4o")], ReportConfig(model_prices=_PRICES))
    assert report.runs[0].cost_usd == pytest.approx(12.50)
    assert report.total_cost_usd == pytest.approx(12.50)


def test_empty_prices_yield_none() -> None:
    report = build_report([_run_with_call("gpt-4o")], ReportConfig())
    assert report.runs[0].cost_usd is None
    assert report.total_cost_usd is None


def test_unmatched_model_yields_none() -> None:
    report = build_report([_run_with_call("some-other-model")], ReportConfig(model_prices=_PRICES))
    assert report.runs[0].cost_usd is None


def test_price_for_longest_match_wins() -> None:
    config = ReportConfig(
        model_prices={"gpt-4o": {"input": 1.0, "output": 1.0}, "gpt-4o-mini": {"input": 9.0}}
    )
    assert config.price_for("gpt-4o-mini-2024")["input"] == 9.0


def test_cost_appears_in_feed_facts() -> None:
    report = build_report([_run_with_call("gpt-4o")], ReportConfig(model_prices=_PRICES))
    fact_keys = [key for key, _ in report.feed[0].facts]
    assert "Est. cost" in fact_keys


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
