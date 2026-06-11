"""Tests for the optional LLM result-summarization module."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

import pytest  # noqa: E402

from agent_panorama.layers import summary as summarize  # noqa: E402


def test_one_line_flattens_blocks_and_whitespace() -> None:
    assert summarize._one_line([{"text": "Showed  the"}, {"text": "stations.\n"}]) == (
        "Showed the stations."
    )
    assert summarize._one_line("  multi\n  line  ") == "multi line"


def test_summarize_result_empty_returns_none() -> None:
    assert summarize.summarize_result("   ") is None


def test_summarize_result_caps_input(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_invoke(model: str, snippet: str) -> str:
        captured["snippet"] = snippet
        return "Did the thing."

    monkeypatch.setattr(summarize, "_invoke", fake_invoke)
    result = summarize.summarize_result("x" * 5000, model="test:model")
    assert result == "Did the thing."
    assert len(captured["snippet"]) == summarize.MAX_INPUT_CHARS


def test_summarize_result_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(model: str, snippet: str) -> str:
        raise RuntimeError("provider down")

    monkeypatch.setattr(summarize, "_invoke", boom)
    # Failure must never break a report — it falls back to None.
    assert summarize.summarize_result("some result", model="test:model") is None


def test_build_exchange_captures_full_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summarize, "_invoke", lambda model, snippet: "Did it.")
    exchange = summarize.build_exchange("a long result", model="test:model")
    assert exchange.system_prompt == summarize._SYSTEM_PROMPT
    assert exchange.input_text == "a long result"
    assert exchange.output == "Did it."
    assert exchange.error is None


def test_build_exchange_records_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(model: str, snippet: str) -> str:
        raise RuntimeError("provider down")

    monkeypatch.setattr(summarize, "_invoke", boom)
    exchange = summarize.build_exchange("result", model="test:model")
    assert exchange.output is None
    assert "provider down" in (exchange.error or "")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


def test_summarize_session_uses_session_prompt(monkeypatch) -> None:
    captured = {}

    def fake_invoke_with(model: str, snippet: str, system_prompt: str) -> str:
        captured["prompt"] = system_prompt
        return "Helped the user with the SSO reset."

    monkeypatch.setattr(summarize, "_invoke_with", fake_invoke_with)
    result = summarize.summarize_session("1. asked: why? → no tools → result: because")
    assert result == "Helped the user with the SSO reset."
    assert captured["prompt"] == summarize._SESSION_SYSTEM_PROMPT


def test_summarize_session_caps_input(monkeypatch) -> None:
    seen = {}

    def fake_invoke_with(model: str, snippet: str, system_prompt: str) -> str:
        seen["len"] = len(snippet)
        return "ok"

    monkeypatch.setattr(summarize, "_invoke_with", fake_invoke_with)
    summarize.summarize_session("x" * 5000)
    assert seen["len"] == summarize.MAX_INPUT_CHARS


def test_summarize_session_swallows_errors(monkeypatch) -> None:
    def boom(model: str, snippet: str, system_prompt: str) -> str:
        raise RuntimeError("no api key")

    monkeypatch.setattr(summarize, "_invoke_with", boom)
    exchange = summarize.build_session_exchange("some transcript")
    assert exchange.output is None
    assert "no api key" in (exchange.error or "")


def test_summarize_session_empty_transcript() -> None:
    exchange = summarize.build_session_exchange("   ")
    assert exchange.output is None
    assert "empty transcript" in (exchange.error or "")


def test_back_compat_shim_reexports_the_layer() -> None:
    from agent_panorama import summarize as shim

    assert shim.summarize_result is summarize.summarize_result
    assert shim.build_session_exchange is summarize.build_session_exchange
    assert shim.SummaryExchange is summarize.SummaryExchange
