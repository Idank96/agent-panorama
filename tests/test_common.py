"""Tests for shared parsing helpers (text/message extraction, tokens, time)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

import pytest  # noqa: E402

from agent_panorama.parsers.common import (  # noqa: E402
    extract_tokens,
    parse_time,
    summarize_outcome,
    summarize_request,
)


def test_summarize_request_from_messages_dict() -> None:
    payload = {"messages": [{"type": "human", "content": "Book me a flight"}]}
    assert summarize_request(payload) == "Book me a flight"


def test_summarize_request_from_tuple_messages() -> None:
    payload = {"messages": [["human", "Book a flight"], ["ai", "Sure"]]}
    assert summarize_request(payload) == "Book a flight"


def test_summarize_request_handles_double_encoded_json() -> None:
    # Real Langfuse exports store input as a JSON-encoded JSON string.
    inner = json.dumps({"messages": [["human", "What's the weather?"], ["ai", "ok"]]})
    double = json.dumps(inner)
    assert summarize_request(double) == "What's the weather?"


def test_summarize_outcome_picks_last_ai_message() -> None:
    payload = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "first"},
            {"role": "assistant", "content": "final answer"},
        ]
    }
    assert summarize_outcome(payload) == "final answer"


def test_summarize_request_flattens_content_blocks() -> None:
    payload = {"messages": [{"type": "human", "content": [{"type": "text", "text": "hello"}]}]}
    assert summarize_request(payload) == "hello"


def test_summarize_falls_back_to_plain_text() -> None:
    assert summarize_request("just a string") == "just a string"


def test_summarize_outcome_extracts_result_field() -> None:
    # LangGraph state has no messages; the result lives in a `report` field.
    assert summarize_outcome({"report": "Daily summary ready."}) == "Daily summary ready."


class _FakeMessage:
    """Stand-in for a LangChain BaseMessage: .content and .type attributes."""

    def __init__(self, type_: str, content: str) -> None:
        self.type = type_
        self.content = content


def test_summarize_request_from_langchain_message_objects() -> None:
    # Live mode hands over raw LangGraph state with message *objects*, not dicts.
    payload = {"messages": [_FakeMessage("human", "Analyze channel t-ai-jane")]}
    assert summarize_request(payload) == "Analyze channel t-ai-jane"


def test_summarize_outcome_from_langchain_message_objects() -> None:
    payload = {
        "messages": [
            _FakeMessage("human", "status?"),
            _FakeMessage("ai", "Candidate is waiting on us."),
        ]
    }
    assert summarize_outcome(payload) == "Candidate is waiting on us."


def test_summarize_request_does_not_dump_secrets() -> None:
    # A state payload with no recognizable ask must not leak embedded secrets.
    state = {"config": {}, "slack_client": {"token": "xoxb-SECRET-123"}, "channels": []}
    summary = summarize_request(state)
    assert "xoxb" not in summary
    assert "SECRET" not in summary
    assert summary.startswith("state with fields:")


def test_extract_tokens_key_variants() -> None:
    assert extract_tokens({"input": 10, "output": 5}) == (10, 5)
    assert extract_tokens({"promptTokens": 7, "completionTokens": 3}) == (7, 3)
    assert extract_tokens({"input_tokens": 2, "output_tokens": 9}) == (2, 9)
    assert extract_tokens(None) == (0, 0)


def test_parse_time_iso_and_epoch() -> None:
    assert parse_time("2026-05-20T09:15:00Z") is not None
    assert parse_time(1_700_000_000) is not None
    assert parse_time("not-a-time") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
