"""Tests for the blueprint-driven value-definition interview."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

import pytest  # noqa: E402

from agent_panorama.layers.value.context import ValueContext  # noqa: E402
from agent_panorama.layers.value.interview import (  # noqa: E402
    MAX_QUESTIONS,
    InterviewTurn,
    advance_interview,
    context_from_payload,
    step_to_dict,
    suggest_options,
    turns_from_payload,
)


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


def _required() -> ValueContext:
    return ValueContext(
        domain="support",
        user_goal="resolve the issue",
        success_criteria=["resolved", "no repeat contact"],
        custom_dimensions={"empathy": "warmth"},
    )


def _full() -> ValueContext:
    ctx = _required()
    ctx.served_user = "a frustrated customer"
    ctx.failure_modes = ["wrong refund amount"]
    ctx.stakes_good = "saves time"
    ctx.stakes_bad = "chargeback"
    return ctx


def test_first_gap_is_the_agent_domain() -> None:
    step = advance_interview("Support Bot", [], ValueContext(), model="bogus:none")
    assert step.done is False
    assert step.object_key == "agent"
    assert step.field_name == "domain"
    assert step.input_kind == "text"
    assert step.suggestions


def test_gap_advances_to_success_criteria_once_goal_is_set() -> None:
    partial = ValueContext(domain="support", user_goal="resolve")
    step = advance_interview("Support Bot", [], partial, model="bogus:none")
    assert step.object_key == "success_criteria"
    assert step.input_kind == "list"


def test_required_complete_moves_to_recommended_not_done() -> None:
    step = advance_interview("Support Bot", [], _required(), model="bogus:none")
    assert step.done is False
    assert step.object_key in {"user", "failure_modes", "stakes"}


def test_everything_filled_completes_with_recap() -> None:
    step = advance_interview("Support Bot", [], _full(), model="bogus:none")
    assert step.done is True
    assert step.recap


def test_model_phrasing_used_but_target_comes_from_the_gap() -> None:
    # Model tries to mark done and pick a different field; the gap wins.
    chat = _FakeChat(
        {
            "done": True,
            "field": "custom_dimensions",
            "prompt": "What does this agent do for people?",
            "suggestions": ["IT helpdesk", "billing support"],
        }
    )
    step = advance_interview("Support Bot", [], ValueContext(), chat_model=chat)
    assert step.done is False
    assert step.field_name == "domain"  # from the gap, not the model
    assert step.object_key == "agent"
    assert step.prompt == "What does this agent do for people?"  # phrasing from the model
    assert step.suggestions == ["IT helpdesk", "billing support"]


def test_recommended_gaps_skipped_after_question_cap() -> None:
    transcript = [InterviewTurn("x", "?", str(i)) for i in range(MAX_QUESTIONS)]
    step = advance_interview("Support Bot", transcript, _required(), model="bogus:none")
    assert step.done is True  # only recommended gaps remain, and we're at the cap


def test_required_gaps_asked_even_past_the_cap() -> None:
    transcript = [InterviewTurn("x", "?", str(i)) for i in range(MAX_QUESTIONS + 3)]
    step = advance_interview("Support Bot", transcript, ValueContext(), model="bogus:none")
    assert step.done is False  # domain is required; the cap never skips required
    assert step.field_name == "domain"


def test_suggest_uses_model_then_falls_back() -> None:
    chat = _FakeChat({"suggestions": ["a", "b", "c"]})
    options = suggest_options("Bot", ValueContext(), "domain", "q?", chat_model=chat)
    assert options == ["a", "b", "c"]
    fallback = suggest_options("Bot", ValueContext(), "domain", "q?", model="bogus:none")
    assert len(fallback) >= 1


def test_payload_helpers_round_trip_new_fields() -> None:
    ctx = context_from_payload(
        {
            "domain": "support",
            "served_user": "a customer",
            "failure_modes": ["wrong amount"],
            "stakes_good": "saves time",
        }
    )
    assert ctx.served_user == "a customer"
    assert ctx.failure_modes == ["wrong amount"]

    turns = turns_from_payload([{"field": "domain", "prompt": "q", "answer": "support"}])
    assert turns[0].field_name == "domain"


def test_step_to_dict_carries_object_key() -> None:
    step = advance_interview("Support Bot", [], ValueContext(), model="bogus:none")
    payload = step_to_dict(step)
    assert payload["field"] == "domain"
    assert payload["object_key"] == "agent"
    assert set(payload) == {
        "done",
        "field",
        "object_key",
        "prompt",
        "help",
        "input_kind",
        "suggestions",
        "recap",
    }


def test_interview_endpoint_smoke() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from agent_panorama.config import ReportConfig
    from agent_panorama.live.server import RunStore, create_app

    client = TestClient(create_app(ReportConfig(), RunStore(), Path(__file__).resolve().parent))
    adv = client.post(
        "/api/value-interview",
        json={"agent_name": "Support Bot", "transcript": [], "current": {}, "action": "advance"},
    ).json()
    assert adv["field"] == "domain"
    assert adv["object_key"] == "agent"
    assert adv["done"] is False

    sug = client.post(
        "/api/value-interview",
        json={
            "agent_name": "Support Bot",
            "current": {},
            "action": "suggest",
            "question": {"field": "domain", "prompt": "what domain?"},
        },
    ).json()
    assert isinstance(sug["suggestions"], list)
    assert len(sug["suggestions"]) >= 1


def test_value_config_response_includes_blueprint() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from agent_panorama.config import ReportConfig
    from agent_panorama.live.server import RunStore, create_app

    client = TestClient(create_app(ReportConfig(), RunStore(), Path(__file__).resolve().parent))
    data = client.get("/api/value-config").json()
    assert "blueprint" in data
    keys = [obj["key"] for obj in data["blueprint"]]
    assert keys[0] == "agent"
    assert "failure_modes" in keys and "stakes" in keys
