"""Tests for Markdown and HTML rendering."""

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
from agent_panorama.models import AgentRun, Report, Step  # noqa: E402
from agent_panorama.render import render  # noqa: E402


def _report():
    payload = json.loads((_bootstrap.EXAMPLES / "langfuse_traces.json").read_text("utf-8"))
    runs = parsers.parse(payload, input_type="langfuse")
    return build_report(runs, ReportConfig())


def _step_report(model_calls: int = 3, tokens: int = 0) -> Report:
    step = Step(name="analyze", model_calls=model_calls, tokens=tokens)
    return Report(runs=[AgentRun(run_id="r", name="agent", steps=[step])], decision_log=[])


def test_markdown_contains_sections() -> None:
    md = render(_report(), ReportConfig(), "md")
    assert "# Agent Activity Report" in md
    assert "## Summary" in md
    assert "## Decision Log" not in md
    assert "## Anomalies" not in md
    assert "research-assistant" in md


def test_markdown_shows_step_narrative() -> None:
    md = render(_report(), ReportConfig(), "md")
    assert "Total steps" in md
    assert "What it did, step by step:" in md


def test_minimal_detail_condenses_result() -> None:
    raw = "📋 Here are all the open support tickets: | Station | Type | | --- | --- |"
    report = Report(runs=[AgentRun(run_id="r", name="agent", output_text=raw)], decision_log=[])
    minimal = render(report, ReportConfig(detail="minimal"), "md")
    standard = render(report, ReportConfig(detail="standard"), "md")
    assert "**Result:** Here are all the open support tickets." in minimal
    assert "| Station |" not in minimal  # data table dropped
    assert "| Station |" in standard  # standard keeps the full result


def test_minimal_prefers_llm_summary_when_present() -> None:
    raw = "📋 Here are all the open support tickets: | Station | Type |"
    run = AgentRun(
        run_id="r",
        name="agent",
        output_text=raw,
        result_summary="Showed all the open support tickets.",
    )
    report = Report(runs=[run], decision_log=[])
    minimal = render(report, ReportConfig(detail="minimal"), "md")
    standard = render(report, ReportConfig(detail="standard"), "md")
    assert "**Result:** Showed all the open support tickets." in minimal
    # Standard ignores the summary and keeps the full result.
    assert "| Station |" in standard


def test_detail_levels_control_step_context() -> None:
    minimal = render(_step_report(tokens=500), ReportConfig(detail="minimal"), "md")
    standard = render(_step_report(tokens=500), ReportConfig(detail="standard"), "md")
    richer = render(_step_report(tokens=500), ReportConfig(detail="richer"), "md")
    # minimal < standard < richer in detail shown per step.
    assert "model call" not in minimal and "500 tokens" not in minimal
    assert "3 model calls" in standard and "500 tokens" not in standard
    assert "3 model calls" in richer and "500 tokens" in richer


def test_html_is_self_contained() -> None:
    html = render(_report(), ReportConfig(), "html")
    assert "<!DOCTYPE html>" in html
    assert "<style>" in html
    # No external resources referenced.
    assert "http://" not in html.replace("http://www.w3.org", "")
    assert "src=" not in html
    assert "human-escalated" in html


def test_html_escapes_content() -> None:
    config = ReportConfig()
    payload = {
        "id": "t",
        "name": "x<script>",
        "input": "<b>hi</b>",
        "output": "ok",
        "observations": [],
    }
    runs = parsers.parse(payload, input_type="langfuse")
    html = render(build_report(runs, config), config, "html")
    assert "<script>" not in html.split("<style>")[0]
    assert "&lt;script&gt;" in html


def test_unknown_format_raises() -> None:
    with pytest.raises(ValueError):
        render(_report(), ReportConfig(), "pdf")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
