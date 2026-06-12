"""Tests for the guided value-definition interview."""

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


def _full_context() -> ValueContext:
    return ValueContext(
        domain="support",
        user_goal="resolve the issue",
        success_criteria=["resolved", "no repeat contact"],
        custom_dimensions={"empathy": "warmth"},
    )


def test_fallback_asks_domain_first_without_provider() -> None:
    step = advance_interview("Support Bot", [], ValueContext(), model="bogus:none")
    assert step.done is False
    assert step.field_name == "domain"
    assert step.input_kind == "text"
    assert step.suggestions  # static examples


def test_fallback_orders_fields_then_completes() -> None:
    partial = ValueContext(domain="support", user_goal="resolve")
    step = advance_interview("Support Bot", [], partial, model="bogus:none")
    assert step.field_name == "success_criteria"
    assert step.input_kind == "list"

    done = advance_interview("Support Bot", [], _full_context(), model="bogus:none")
    assert done.done is True
    assert done.recap


def test_llm_step_is_normalized() -> None:
    chat = _FakeChat(
        {
            "done": False,
            "field": "success_criteria",
            "prompt": "What marks a good outcome?",
            "help": "These are reported per conversation.",
            "suggestions": ["resolved", "no escalation"],
        }
    )
    step = advance_interview("Support Bot", [], ValueContext(domain="x"), chat_model=chat)
    assert step.field_name == "success_criteria"
    assert step.input_kind == "list"
    assert step.prompt.startswith("What marks")


def test_invalid_field_coerced_to_next_missing() -> None:
    chat = _FakeChat({"done": False, "field": "not_a_field", "prompt": "?"})
    step = advance_interview("Support Bot", [], ValueContext(), chat_model=chat)
    assert step.field_name == "domain"


def test_done_overridden_when_minimums_unmet() -> None:
    chat = _FakeChat({"done": True, "recap": "all set"})
    step = advance_interview("Support Bot", [], ValueContext(domain="only"), chat_model=chat)
    assert step.done is False
    assert step.field_name == "user_goal"


def test_done_respected_when_minimums_met() -> None:
    chat = _FakeChat({"done": True, "recap": "complete"})
    step = advance_interview("Support Bot", [], _full_context(), chat_model=chat)
    assert step.done is True
    assert step.recap == "complete"


def test_question_cap_forces_completion() -> None:
    transcript = [InterviewTurn("domain", "?", str(i)) for i in range(MAX_QUESTIONS)]
    step = advance_interview("Support Bot", transcript, ValueContext(), model="bogus:none")
    assert step.done is True


def test_suggest_uses_model_then_falls_back() -> None:
    chat = _FakeChat({"suggestions": ["a", "b", "c"]})
    options = suggest_options("Bot", ValueContext(), "domain", "q?", chat_model=chat)
    assert options == ["a", "b", "c"]
    # No provider -> static fallback for the field.
    fallback = suggest_options("Bot", ValueContext(), "domain", "q?", model="bogus:none")
    assert len(fallback) >= 1


def test_payload_helpers_round_trip() -> None:
    ctx = context_from_payload(
        {
            "domain": "support",
            "user_goal": "resolve",
            "success_criteria": ["a"],
            "custom_dimensions": {"empathy": "warmth"},
        }
    )
    assert ctx.domain == "support"
    assert ctx.success_criteria == ["a"]

    turns = turns_from_payload([{"field": "domain", "prompt": "q", "answer": "support"}])
    assert turns[0].field_name == "domain"
    assert turns[0].answer == "support"


def test_step_to_dict_uses_field_json_key() -> None:
    step = advance_interview("Support Bot", [], ValueContext(), model="bogus:none")
    payload = step_to_dict(step)
    assert payload["field"] == "domain"
    assert set(payload) == {"done", "field", "prompt", "help", "input_kind", "suggestions", "recap"}


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
