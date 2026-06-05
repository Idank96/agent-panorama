"""Tests for live mode: wire format, callback handler, store, and server."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

import pytest  # noqa: E402

from agent_panorama.config import ReportConfig  # noqa: E402
from agent_panorama.live import transport  # noqa: E402
from agent_panorama.live.handler import PanoramaCallbackHandler  # noqa: E402
from agent_panorama.live.serde import WIRE_VERSION, run_from_dict, run_to_dict  # noqa: E402
from agent_panorama.models import AgentRun, LLMCall, Outcome, Step, ToolCall  # noqa: E402

_T0 = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 1, 9, 0, 42, tzinfo=timezone.utc)


def _full_run() -> AgentRun:
    return AgentRun(
        run_id="run-1",
        name="research-assistant",
        input_text="What is the weather in Paris?",
        output_text="It is sunny, 24°C.",
        start_time=_T0,
        end_time=_T1,
        outcome=Outcome.SUCCESS,
        steps=[Step(name="get_weather", kind="tool", start_time=_T0, tool_calls=1)],
        tool_calls=[
            ToolCall(
                name="get_weather",
                arguments={"city": "Paris"},
                output="sunny, 24°C",
                timestamp=_T0,
                latency_ms=120.5,
            )
        ],
        llm_calls=[
            LLMCall(
                name="ChatModel",
                model="gpt-4o-mini",
                input_tokens=320,
                output_tokens=48,
                timestamp=_T0,
                latency_ms=900.0,
            )
        ],
        retry_count=1,
        fallback_used=True,
        error_messages=["transient timeout"],
        anomalies=["1 retry"],
        cost_usd=0.0012,
    )


def test_serde_round_trip_preserves_run() -> None:
    original = _full_run()
    restored = run_from_dict(run_to_dict(original))
    assert restored == original


def test_serde_tolerates_malformed_payload() -> None:
    run = run_from_dict({"run_id": 7, "outcome": "not-a-real-outcome", "tool_calls": "oops"})
    assert run.run_id == "7"
    assert run.outcome is Outcome.UNKNOWN
    assert run.tool_calls == []


class _Capture:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict]] = []

    def __call__(self, url: str, payload: dict, timeout: float = 2.0) -> bool:
        self.posts.append((url, payload))
        return True


@pytest.fixture()
def capture(monkeypatch: pytest.MonkeyPatch) -> _Capture:
    captured = _Capture()
    monkeypatch.setattr(transport, "post_run", captured)
    return captured


class _FakeLLMResult:
    def __init__(self, token_usage: dict) -> None:
        self.llm_output = {"token_usage": token_usage}
        self.generations: list = []


def test_handler_builds_and_posts_completed_run(capture: _Capture) -> None:
    pytest.importorskip("langchain_core")
    handler = PanoramaCallbackHandler(endpoint="http://localhost:9999")
    root, child_llm, child_tool = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    handler.on_chain_start(
        {"name": "research-assistant"},
        {"messages": [{"role": "user", "content": "Weather in Paris?"}]},
        run_id=root,
        parent_run_id=None,
    )
    handler.on_chat_model_start(
        {"kwargs": {"model": "gpt-4o-mini"}}, [], run_id=child_llm, parent_run_id=root
    )
    handler.on_llm_end(
        _FakeLLMResult({"prompt_tokens": 320, "completion_tokens": 48}), run_id=child_llm
    )
    handler.on_tool_start({"name": "get_weather"}, "Paris", run_id=child_tool, parent_run_id=root)
    handler.on_tool_end("sunny, 24°C", run_id=child_tool)
    handler.on_chain_end(
        {"messages": [{"role": "assistant", "content": "It is sunny in Paris."}]}, run_id=root
    )

    assert len(capture.posts) == 1
    url, payload = capture.posts[0]
    assert url == "http://localhost:9999/api/runs"
    assert payload["version"] == WIRE_VERSION
    run = run_from_dict(payload["run"])
    assert run.name == "research-assistant"
    assert run.input_text == "Weather in Paris?"
    assert run.output_text == "It is sunny in Paris."
    assert [c.name for c in run.tool_calls] == ["get_weather"]
    assert run.llm_calls[0].model == "gpt-4o-mini"
    assert (run.llm_calls[0].input_tokens, run.llm_calls[0].output_tokens) == (320, 48)
    assert run.steps and run.steps[0].kind == "tool"
    assert run.start_time is not None and run.end_time is not None


def test_handler_posts_failed_run_on_chain_error(capture: _Capture) -> None:
    pytest.importorskip("langchain_core")
    handler = PanoramaCallbackHandler()
    root = uuid.uuid4()
    handler.on_chain_start({"name": "research-assistant"}, "task", run_id=root, parent_run_id=None)
    handler.on_chain_error(RuntimeError("model unavailable"), run_id=root)

    assert len(capture.posts) == 1
    run = run_from_dict(capture.posts[0][1]["run"])
    assert run.error_messages == ["model unavailable"]
    assert run.output_text == ""


def test_handler_ignores_non_root_chain_events(capture: _Capture) -> None:
    pytest.importorskip("langchain_core")
    handler = PanoramaCallbackHandler()
    root, child = uuid.uuid4(), uuid.uuid4()
    handler.on_chain_start({"name": "research-assistant"}, "task", run_id=root, parent_run_id=None)
    handler.on_chain_start({"name": "subgraph"}, {}, run_id=child, parent_run_id=root)
    handler.on_chain_end({}, run_id=child)
    assert capture.posts == []
    handler.on_chain_end({"result": "done"}, run_id=root)
    assert len(capture.posts) == 1


def test_transport_failure_never_raises() -> None:
    assert transport.post_run("http://127.0.0.1:1/api/runs", {"version": 1}, timeout=0.2) is False


def test_run_store_replaces_and_trims() -> None:
    pytest.importorskip("fastapi")
    from agent_panorama.live.server import RunStore

    store = RunStore(max_runs=2)
    store.add(AgentRun(run_id="a", name="research-assistant"))
    store.add(AgentRun(run_id="b", name="research-assistant"))
    store.add(AgentRun(run_id="a", name="research-assistant", output_text="updated"))
    assert [run.run_id for run in store.snapshot()] == ["b", "a"]
    store.add(AgentRun(run_id="c", name="research-assistant"))
    assert [run.run_id for run in store.snapshot()] == ["a", "c"]


def test_server_ingests_and_reports() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from agent_panorama.live.server import RunStore, create_app

    app = create_app(ReportConfig(), RunStore())
    client = TestClient(app)

    posted = client.post(
        "/api/runs", json={"version": WIRE_VERSION, "run": run_to_dict(_full_run())}
    )
    assert posted.status_code == 200
    assert posted.json() == {"ok": True, "run_id": "run-1"}

    report = client.get("/api/report").json()
    assert set(report) == {
        "generated_at",
        "time_range",
        "totals",
        "feed",
        "rollups",
        "decision_log",
    }
    assert report["totals"]["runs"] == 1
    assert report["feed"][0]["run_id"] == "run-1"
    assert report["feed"][0]["agent_name"] == "research-assistant"
    assert report["feed"][0]["outcome"] == "success"

    health = client.get("/healthz").json()
    assert health == {"status": "ok", "runs": 1}


def test_serve_fails_fast_when_port_is_taken() -> None:
    pytest.importorskip("fastapi")
    import socket

    from agent_panorama.live.server import _ensure_port_free

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        taken_port = holder.getsockname()[1]
        with pytest.raises(OSError, match=f"--port {taken_port + 1}"):
            _ensure_port_free("127.0.0.1", taken_port)


def test_server_root_without_bundled_dashboard_explains_itself() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from agent_panorama.live.server import RunStore, create_app

    client = TestClient(create_app(ReportConfig(), RunStore()))
    response = client.get("/")
    assert response.status_code == 200


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
