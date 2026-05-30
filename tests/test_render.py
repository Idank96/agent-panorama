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
from agent_panorama.render import render  # noqa: E402


def _report():
    payload = json.loads((_bootstrap.EXAMPLES / "langfuse_traces.json").read_text("utf-8"))
    runs = parsers.parse(payload, input_type="langfuse")
    return build_report(runs, ReportConfig())


def test_markdown_contains_sections() -> None:
    md = render(_report(), ReportConfig(), "md")
    assert "# Agent Activity Report" in md
    assert "## Summary" in md
    assert "## Decision Log" in md
    assert "## Anomalies" in md
    assert "research-assistant" in md


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
