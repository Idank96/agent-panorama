"""Tests for the Langfuse and LangSmith parsers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402

import pytest  # noqa: E402

from agent_panorama import parsers  # noqa: E402
from agent_panorama.models import AgentRun  # noqa: E402


def _load(name: str) -> object:
    return json.loads((_bootstrap.EXAMPLES / name).read_text(encoding="utf-8"))


def test_langfuse_batch_parses_all_traces() -> None:
    runs = parsers.parse(_load("langfuse_traces.json"), input_type="langfuse")
    assert len(runs) == 3
    assert all(isinstance(r, AgentRun) for r in runs)


def test_langfuse_extracts_tools_and_tokens() -> None:
    runs = parsers.parse(_load("langfuse_traces.json"), input_type="langfuse")
    research = next(r for r in runs if r.name == "research-assistant")
    tool_names = [c.name for c in research.tool_calls]
    assert "web_search" in tool_names
    assert "summarize_text" in tool_names
    # GENERATION tool_calls should not double-count when spans exist.
    assert tool_names.count("web_search") == 1
    assert research.total_tokens == 800 + 120 + 1000 + 100


def test_langfuse_single_trace_supported() -> None:
    single = _load("langfuse_traces.json")[0]  # type: ignore[index]
    runs = parsers.parse(single, input_type="langfuse")
    assert len(runs) == 1


def test_langfuse_error_observation_recorded() -> None:
    runs = parsers.parse(_load("langfuse_traces.json"), input_type="langfuse")
    weather = next(r for r in runs if r.name == "weather-assistant")
    assert weather.error_messages
    assert any(c.status == "error" for c in weather.tool_calls)


def test_langsmith_run_tree_flattens() -> None:
    runs = parsers.parse(_load("langsmith_runs.json"), input_type="langsmith")
    assert len(runs) == 1
    run = runs[0]
    assert run.name == "recipe-assistant"
    assert {c.name for c in run.tool_calls} == {"web_search", "send_email"}
    assert run.total_tokens == 780 + 110 + 950 + 70


def test_unsupported_input_type_raises() -> None:
    with pytest.raises(ValueError):
        parsers.parse({}, input_type="nope")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
