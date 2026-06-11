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


def _langgraph_trace() -> dict:
    """A LangGraph-shaped trace: named graph nodes, no TOOL observations."""
    return {
        "id": "lg1",
        "name": "LangGraph",
        "timestamp": "2026-05-20T10:00:00Z",
        "input": "{}",
        "output": {"report": "All done."},
        "observations": [
            {
                "id": "root",
                "type": "CHAIN",
                "name": "LangGraph",
                "startTime": "2026-05-20T10:00:00Z",
            },
            {
                "id": "n1",
                "type": "CHAIN",
                "name": "retrieve_data",
                "parentObservationId": "root",
                "startTime": "2026-05-20T10:00:01Z",
            },
            {
                "id": "n2",
                "type": "CHAIN",
                "name": "analyze",
                "parentObservationId": "root",
                "startTime": "2026-05-20T10:00:02Z",
            },
            {
                "id": "g1",
                "type": "GENERATION",
                "name": "ChatModel",
                "parentObservationId": "n2",
                "startTime": "2026-05-20T10:00:03Z",
                "inputUsage": 100,
                "outputUsage": 20,
            },
            {
                "id": "n3",
                "type": "CHAIN",
                "name": "respond",
                "parentObservationId": "root",
                "startTime": "2026-05-20T10:00:04Z",
            },
        ],
    }


def test_langfuse_graph_nodes_become_steps() -> None:
    run = parsers.parse(_langgraph_trace(), input_type="langfuse")[0]
    # No tools, yet the agent's work is narrated as its ordered graph nodes.
    assert len(run.tool_calls) == 0
    assert [s.name for s in run.steps] == ["retrieve_data", "analyze", "respond"]
    analyze = next(s for s in run.steps if s.name == "analyze")
    assert analyze.model_calls == 1
    assert analyze.tokens == 120
    assert run.output_text == "All done."


def test_langfuse_missing_output_is_empty_not_none() -> None:
    trace = {
        "id": "no-out",
        "name": "support-agent",
        "timestamp": "2026-05-20T10:00:00Z",
        "input": {"task": "Issue a refund for order ORD-5567."},
        "observations": [
            {
                "id": "e1",
                "type": "SPAN",
                "name": "process_refund",
                "startTime": "2026-05-20T10:00:01Z",
                "level": "ERROR",
                "statusMessage": "Payment gateway rejected the refund",
            }
        ],
    }
    run = parsers.parse(trace, input_type="langfuse")[0]
    assert run.output_text == ""
    assert run.error_messages


def test_langfuse_tool_runs_expose_steps() -> None:
    research = next(
        r
        for r in parsers.parse(_load("langfuse_traces.json"), input_type="langfuse")
        if r.name == "research-assistant"
    )
    assert len(research.steps) == len(research.tool_calls) >= 1


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
    assert {s.name for s in run.steps} == {"web_search", "send_email"}
    assert run.total_tokens == 780 + 110 + 950 + 70


def test_unsupported_input_type_raises() -> None:
    with pytest.raises(ValueError):
        parsers.parse({}, input_type="nope")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


def test_langfuse_extracts_session_and_user() -> None:
    from agent_panorama.parsers import langfuse

    trace = {"id": "t1", "name": "kb-assistant", "sessionId": "sess-1", "userId": "user-1"}
    run = langfuse.parse(trace)[0]
    assert run.session_id == "sess-1"
    assert run.user_id == "user-1"


def test_langfuse_falls_back_to_metadata_identity() -> None:
    from agent_panorama.parsers import langfuse

    trace = {
        "id": "t1",
        "name": "kb-assistant",
        "metadata": {"session_id": "m-sess", "user_id": "m-user"},
    }
    run = langfuse.parse(trace)[0]
    assert run.session_id == "m-sess"
    assert run.user_id == "m-user"


def test_langsmith_ignores_project_session_id() -> None:
    from agent_panorama.parsers import langsmith

    root = {
        "id": "r1",
        "name": "kb-assistant",
        "run_type": "chain",
        "session_id": "project-uuid-not-a-conversation",
        "extra": {"metadata": {"thread_id": "thread-1", "user_id": "user-1"}},
    }
    run = langsmith.parse([root])[0]
    assert run.session_id == "thread-1"
    assert run.user_id == "user-1"


def test_langsmith_no_metadata_means_no_session() -> None:
    from agent_panorama.parsers import langsmith

    root = {"id": "r1", "name": "kb-assistant", "run_type": "chain", "session_id": "project-uuid"}
    run = langsmith.parse([root])[0]
    assert run.session_id is None
    assert run.user_id is None
