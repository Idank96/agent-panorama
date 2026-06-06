"""Tests for the value layer's judge, prompts, and context handling."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

import pytest  # noqa: E402

from agent_panorama.layers.value import (  # noqa: E402
    Exchange,
    ValueContext,
    build_judge_messages,
    exchanges_from_turns,
    judge_session,
)
from agent_panorama.layers.value.judge import (  # noqa: E402
    MAX_EXCHANGE_CHARS,
    MAX_TRANSCRIPT_CHARS,
)
from agent_panorama.layers.value.prompts import format_context  # noqa: E402
from agent_panorama.models import AgentRun, ValueJudgment  # noqa: E402


def _judgment_dict(**overrides) -> dict:
    base = {
        "outcome": "User got a working command.",
        "value_delivered": ["Provided a runnable one-liner."],
        "value_lost": [],
        "recommended_fixes": [],
        "goal_completion": 8,
        "response_quality": 7,
        "efficiency": 9,
        "overall_score": 8,
        "rationale": "Solved the task quickly.",
        "custom_scores": {},
        "criteria_verdicts": {},
    }
    base.update(overrides)
    return base


class StubStructuredModel:
    def __init__(self, result: object) -> None:
        self.result = result
        self.messages: list[dict[str, str]] | None = None

    def invoke(self, messages: list[dict[str, str]]) -> object:
        self.messages = messages
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class StubChatModel:
    def __init__(self, result: object) -> None:
        self.structured = StubStructuredModel(result)
        self.schema: type | None = None

    def with_structured_output(self, schema: type) -> StubStructuredModel:
        self.schema = schema
        return self.structured


def _turn(run_id: str, ask: str, answer: str) -> AgentRun:
    return AgentRun(run_id=run_id, name="tutor", input_text=ask, output_text=answer)


def _context() -> ValueContext:
    return ValueContext(
        domain="insurance claims processing",
        user_goal="file a complete claim without agent help",
        success_criteria=["claim submitted in under 10 minutes"],
        custom_dimensions={"self_service": "Finished without human escalation?"},
    )


def test_judge_session_returns_judgment() -> None:
    exchange = judge_session(
        [_turn("t1", "find big files", "du -ah | sort")],
        chat_model=StubChatModel(_judgment_dict()),
    )
    assert exchange.error is None
    assert isinstance(exchange.judgment, ValueJudgment)
    assert exchange.judgment.overall_score == 8
    assert "overall_score" in (exchange.output or "")


def test_judge_session_sends_transcript_to_model() -> None:
    model = StubChatModel(_judgment_dict())
    judge_session([_turn("t1", "find big files", "du -ah | sort")], chat_model=model)
    assert model.structured.messages is not None
    transcript = model.structured.messages[1]["content"]
    assert "find big files" in transcript
    assert "du -ah | sort" in transcript


def test_judge_session_injects_customer_context() -> None:
    model = StubChatModel(_judgment_dict())
    judge_session([_turn("t1", "start", "form")], context=_context(), chat_model=model)
    assert model.structured.messages is not None
    assert "Value is defined by the customer" in model.structured.messages[0]["content"]
    assert "Customer context:" in model.structured.messages[1]["content"]
    assert "file a complete claim without agent help" in model.structured.messages[1]["content"]


def test_judge_session_empty_turns_records_error() -> None:
    exchange = judge_session([_turn("t1", "", "  ")], chat_model=StubChatModel(_judgment_dict()))
    assert exchange.judgment is None
    assert exchange.output is None
    assert "no usable exchanges" in (exchange.error or "")


def test_judge_session_swallows_model_errors() -> None:
    exchange = judge_session(
        [_turn("t1", "ask", "answer")], chat_model=StubChatModel(RuntimeError("no api key"))
    )
    assert exchange.judgment is None
    assert "no api key" in (exchange.error or "")


def test_exchanges_from_turns_drops_empty_and_truncates() -> None:
    turns = [
        _turn("t1", "x" * (MAX_EXCHANGE_CHARS + 50), "y"),
        _turn("t2", "", ""),
        _turn("t3", "", "answer only"),
    ]
    exchanges = exchanges_from_turns(turns)
    assert len(exchanges) == 2
    assert len(exchanges[0].user_input) == MAX_EXCHANGE_CHARS
    assert exchanges[1].assistant_output == "answer only"


def test_judge_session_caps_transcript() -> None:
    model = StubChatModel(_judgment_dict())
    turns = [_turn(f"t{i}", "q" * 1900, "a" * 1900) for i in range(10)]
    judge_session(turns, chat_model=model)
    assert model.structured.messages is not None
    content = model.structured.messages[1]["content"]
    assert content.endswith("[transcript truncated]")
    assert len(content) <= MAX_TRANSCRIPT_CHARS + len("\n[transcript truncated]")


def test_format_context_includes_all_fields() -> None:
    rendered = format_context(_context())
    assert "insurance claims processing" in rendered
    assert "file a complete claim without agent help" in rendered
    assert "claim submitted in under 10 minutes" in rendered
    assert "self_service" in rendered


def test_build_judge_messages_without_context_is_generic() -> None:
    messages = build_judge_messages([Exchange("start my claim", "Here is the form.")])
    assert "Value is defined by the customer" not in messages[0]["content"]
    assert "Customer context:" not in messages[1]["content"]
    assert "Session transcript:" in messages[1]["content"]


def test_context_merged_over_default() -> None:
    default = _context()
    override = ValueContext(user_goal="student understands the concept")
    merged = override.merged_over(default)
    assert merged.user_goal == "student understands the concept"
    assert merged.domain == "insurance claims processing"
    assert merged.success_criteria == ["claim submitted in under 10 minutes"]
    assert ValueContext(domain="x").merged_over(None).domain == "x"


def test_schema_roundtrips_into_judgment() -> None:
    pytest.importorskip("pydantic")
    from agent_panorama.layers.value._schema import ValueReportSchema

    schema = ValueReportSchema(**_judgment_dict())
    judgment = ValueJudgment(**schema.model_dump())
    assert judgment.overall_score == 8
    assert judgment.value_delivered == ["Provided a runnable one-liner."]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
