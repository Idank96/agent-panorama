"""Tests for the canonical value ontology and value-config persistence."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

import pytest  # noqa: E402

from agent_panorama.config import (  # noqa: E402
    ReportConfig,
    ValueLayerConfig,
    value_config_from_dict,
    value_config_is_empty,
    value_config_to_dict,
)
from agent_panorama.layers.value.context import ValueContext  # noqa: E402
from agent_panorama.layers.value.ontology import (  # noqa: E402
    PRIMITIVES,
    AgentMapping,
    build_agent_mapping,
    context_hash,
    mapping_from_dict,
    mapping_to_dict,
)
from agent_panorama.models import AgentRun, Outcome, ValueJudgment  # noqa: E402


class _FakeStructured:
    def __init__(self, data: dict) -> None:
        self._data = data

    def invoke(self, _messages: object) -> object:
        data = self._data

        class _Result:
            def model_dump(self) -> dict:
                return data

        return _Result()


class _FakeChat:
    def __init__(self, data: dict) -> None:
        self._data = data

    def with_structured_output(self, _schema: object) -> _FakeStructured:
        return _FakeStructured(self._data)


def _context() -> ValueContext:
    return ValueContext(
        domain="customer support",
        user_goal="resolve the user's billing issue",
        success_criteria=["issue resolved without escalation"],
        custom_dimensions={"empathy": "warmth and acknowledgement of the user"},
    )


def test_empty_context_degrades_to_default_without_calling_model() -> None:
    mapping = build_agent_mapping("support-bot", ValueContext(), model="bogus:nope")
    assert mapping.source == "default"
    assert mapping.archetype == "unknown"
    assert mapping.dimension_to_primitive == {}


def test_missing_provider_never_raises_and_degrades() -> None:
    mapping = build_agent_mapping("support-bot", _context(), model="bogus-provider:missing")
    assert mapping.source == "default"
    assert mapping.archetype == "unknown"


def test_auto_map_normalizes_model_output() -> None:
    chat = _FakeChat(
        {
            "archetype": "support",
            "archetype_confidence": 0.9,
            "dimension_to_primitive": {"empathy": "safety_trust", "bogus": "not_a_primitive"},
            "criterion_to_primitive": {"issue resolved without escalation": "autonomy"},
        }
    )
    mapping = build_agent_mapping("support-bot", _context(), chat_model=chat)
    assert mapping.source == "llm"
    assert mapping.archetype == "support"
    assert mapping.dimension_to_primitive == {"empathy": "safety_trust"}
    assert mapping.criterion_to_primitive == {"issue resolved without escalation": "autonomy"}
    assert set(mapping.dimension_to_primitive.values()) <= set(PRIMITIVES)


def test_low_confidence_archetype_falls_back_to_unknown() -> None:
    chat = _FakeChat({"archetype": "support", "archetype_confidence": 0.1})
    mapping = build_agent_mapping("support-bot", _context(), chat_model=chat)
    assert mapping.archetype == "unknown"


def test_unknown_archetype_key_is_rejected() -> None:
    chat = _FakeChat({"archetype": "totally-made-up", "archetype_confidence": 0.99})
    mapping = build_agent_mapping("support-bot", _context(), chat_model=chat)
    assert mapping.archetype == "unknown"


def test_context_hash_is_stable_and_content_sensitive() -> None:
    assert context_hash(_context()) == context_hash(_context())
    assert context_hash(_context()) != context_hash(ValueContext(domain="sales"))
    assert context_hash(None) == context_hash(ValueContext())


def test_mapping_round_trip() -> None:
    mapping = AgentMapping(
        agent_key="support-bot",
        archetype="support",
        archetype_confidence=0.8,
        dimension_to_primitive={"empathy": "safety_trust"},
        source="llm",
    )
    restored = mapping_from_dict(mapping_to_dict(mapping))
    assert restored == mapping


def test_value_config_round_trip() -> None:
    raw = {
        "judge_model": "google_genai:gemini-2.5-flash",
        "max_judgments": 25,
        "include_single_runs": False,
        "default": {"domain": "support", "success_criteria": ["resolved"]},
        "contexts": {
            "support-bot": {
                "user_goal": "resolve billing issues",
                "custom_dimensions": {"empathy": "warmth"},
            }
        },
    }
    config = value_config_from_dict(raw)
    assert config is not None
    again = value_config_from_dict(value_config_to_dict(config))
    assert again == config


def test_value_config_is_empty() -> None:
    assert value_config_is_empty(None)
    assert value_config_is_empty(ValueLayerConfig())
    assert not value_config_is_empty(ValueLayerConfig(default=ValueContext(domain="x")))


def _run(run_id: str, name: str = "support-bot") -> AgentRun:
    return AgentRun(
        run_id=run_id,
        name=name,
        input_text="I was double charged",
        output_text="Refund issued.",
        outcome=Outcome.SUCCESS,
    )


def test_value_config_endpoints_persist_and_reflect() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from agent_panorama.live.server import RunStore, create_app

    tmp = Path(__file__).resolve().parent / "_tmp_value_cfg"
    tmp.mkdir(exist_ok=True)
    for stale in tmp.glob("*.json"):
        stale.unlink()
    store = RunStore()
    store.add(_run("r1"))
    client = TestClient(create_app(ReportConfig(), store, tmp))

    before = client.get("/api/value-config").json()
    assert before["enabled"] is False
    assert {"key": "support-bot", "name": "support-bot"} in before["agents"]
    assert "support" in before["ontology"]["archetypes"]

    body = {"default": {"domain": "support", "user_goal": "resolve the issue"}}
    posted = client.post("/api/value-config", json=body).json()
    assert posted == {"ok": True, "enabled": True}
    assert (tmp / "value_config.json").is_file()

    after = client.get("/api/value-config").json()
    assert after["enabled"] is True
    assert after["config"]["default"]["domain"] == "support"

    for leftover in tmp.glob("*.json"):
        leftover.unlink()
    tmp.rmdir()


def test_apply_value_config_change_maps_and_rejudges(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from agent_panorama.live import server

    monkeypatch.setattr(
        server,
        "build_agent_mapping",
        lambda key, ctx, model: AgentMapping(agent_key=key, archetype="support", source="llm"),
    )

    class _Exchange:
        judgment = ValueJudgment(
            overall_score=7,
            goal_completion=8,
            response_quality=7,
            efficiency=6,
            outcome="resolved",
            rationale="ok",
        )

    monkeypatch.setattr(
        "agent_panorama.layers.value.judge_session",
        lambda turns, context, model: _Exchange(),
    )

    tmp = Path(__file__).resolve().parent / "_tmp_value_apply"
    tmp.mkdir(exist_ok=True)
    for stale in tmp.glob("*.json"):
        stale.unlink()

    store = server.RunStore()
    store.add(_run("r1"))
    store.cache_judgment("r1", 1, _Exchange.judgment)
    config = ReportConfig(value=ValueLayerConfig(default=ValueContext(domain="support")))

    server._apply_value_config_change(store, config, tmp)

    assert store.mapping_entries()["support-bot"][1].archetype == "support"
    assert store.get_judgment("r1") is not None
    assert (tmp / "ontology_map.json").is_file()

    for leftover in tmp.glob("*.json"):
        leftover.unlink()
    tmp.rmdir()


def test_disabling_value_layer_clears_mappings() -> None:
    pytest.importorskip("fastapi")
    from agent_panorama.live import server

    tmp = Path(__file__).resolve().parent / "_tmp_value_off"
    tmp.mkdir(exist_ok=True)
    store = server.RunStore()
    store.cache_mapping("support-bot", "h", AgentMapping(agent_key="support-bot"))
    config = ReportConfig(value=None)

    server._apply_value_config_change(store, config, tmp)

    assert store.mapping_entries() == {}
    assert not (tmp / "ontology_map.json").exists()
    if tmp.exists():
        tmp.rmdir()
