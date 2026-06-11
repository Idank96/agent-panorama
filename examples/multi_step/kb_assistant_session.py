"""Live demo: a RAG support assistant over a help center (retrieval-first style).

Imitates the trace *shape* of a retrieval-augmented support assistant:

- **Simple question**: one semantic search returns cited chunks
  (``[Source N, Page M]: ...``), then the model answers from them.
- **Fallback retrieval chain**: semantic search finds nothing, the agent
  narrows to the current section, then falls back to a raw page lookup
  (a tool with "fallback" in its name flags the run as a fallback path).
- **Recursion limit**: the agent burns its tool budget without converging
  and fails with a recursion-limit error (failed run, several retrievals).
- **Follow-up turn**: answered from conversation context, no retrieval at all.

All four turns share one ``(session_id, user_id)``, so the dashboard rolls
them into a SINGLE feed entry — one user's whole support session — with
an "Interactions: 4 · ..." breakdown and (when a summarize model is
configured) an LLM-phrased session line.

Usage (two terminals):

    agent-panorama serve --open
    python examples/multi_step/kb_assistant_session.py
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_panorama.live.serde import WIRE_VERSION, run_to_dict
from agent_panorama.live.transport import post_run
from agent_panorama.models import AgentRun, LLMCall, ToolCall

ENDPOINT = "http://localhost:8321/api/runs"
_BATCH = uuid.uuid4().hex[:8]

ASSISTANT_MODEL = "claude-sonnet-4-5"
SESSION_ID = f"kb-session-{_BATCH}"
USER = "user-1"


def _assistant_call(
    name: str, start: datetime, offset: int, tokens_in: int, tokens_out: int
) -> LLMCall:
    """One assistant model call at a relative offset within the run."""
    return LLMCall(
        name=name,
        model=ASSISTANT_MODEL,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        timestamp=start + timedelta(seconds=offset),
        latency_ms=2200.0,
    )


def _simple_question_run(now: datetime) -> AgentRun:
    """One retrieval, one cited answer."""
    start = now - timedelta(minutes=7)
    return AgentRun(
        run_id=f"assistant-simple-{_BATCH}",
        name="kb-assistant",
        session_id=SESSION_ID,
        user_id=USER,
        input_text="How do I reset my SSO login?",
        output_text=(
            "Walked the user through it: reset SSO from the admin console under "
            "Security → Single Sign-On (cited pages 42 and 44)."
        ),
        start_time=start,
        end_time=start + timedelta(seconds=9),
        tool_calls=[
            ToolCall(
                name="search_help_center",
                arguments={"query": "reset SSO login", "top_k": 10},
                output="[Source 1, Page 42]: The SSO settings... [Source 2, Page 44]: ...",
                timestamp=start + timedelta(seconds=2),
                latency_ms=1400.0,
            )
        ],
        llm_calls=[
            _assistant_call("choose_retrieval", start, 0, 2100, 80),
            _assistant_call("answer_with_citations", start, 4, 2600, 720),
        ],
    )


def _fallback_chain_run(now: datetime) -> AgentRun:
    """Semantic search misses; the agent narrows scope, then dumps the raw page."""
    start = now - timedelta(minutes=5)
    return AgentRun(
        run_id=f"assistant-fallback-{_BATCH}",
        name="kb-assistant",
        session_id=SESSION_ID,
        user_id=USER,
        input_text="What does the diagram on this page show? (page 87)",
        output_text=(
            "Found it via the raw page text: the diagram traces a webhook delivery "
            "from event to retry (page 87)."
        ),
        start_time=start,
        end_time=start + timedelta(seconds=18),
        tool_calls=[
            ToolCall(
                name="search_help_center",
                arguments={"query": "diagram page 87", "top_k": 10},
                output="No relevant content found.",
                timestamp=start + timedelta(seconds=2),
                latency_ms=1300.0,
            ),
            ToolCall(
                name="search_section",
                arguments={"query": "diagram", "page": 87},
                output="No relevant content found.",
                timestamp=start + timedelta(seconds=6),
                latency_ms=1200.0,
            ),
            ToolCall(
                name="fallback_page_lookup",
                arguments={"page": 87, "pages": 2},
                output="[Source 1, Page 87]: Figure 4.2 — the webhook delivery flow...",
                timestamp=start + timedelta(seconds=10),
                latency_ms=1600.0,
            ),
        ],
        llm_calls=[
            _assistant_call("choose_retrieval", start, 0, 2200, 70),
            _assistant_call("retry_narrower", start, 4, 2400, 60),
            _assistant_call("retry_raw_page", start, 8, 2500, 60),
            _assistant_call("answer_with_citations", start, 12, 3100, 680),
        ],
    )


def _recursion_limit_run(now: datetime) -> AgentRun:
    """The tool budget runs out before the agent converges."""
    start = now - timedelta(minutes=2, seconds=30)
    searches = [
        ToolCall(
            name="search_help_center",
            arguments={"query": query, "top_k": 10},
            output="No relevant content found.",
            timestamp=start + timedelta(seconds=2 + index * 4),
            latency_ms=1300.0,
        )
        for index, query in enumerate(
            ["internal admin password", "master account credentials", "support backdoor login"]
        )
    ]
    return AgentRun(
        run_id=f"assistant-recursion-{_BATCH}",
        name="kb-assistant",
        session_id=SESSION_ID,
        user_id=USER,
        input_text="Give me the internal admin password for the billing console.",
        output_text="",
        start_time=start,
        end_time=start + timedelta(seconds=20),
        tool_calls=searches,
        llm_calls=[
            _assistant_call("choose_retrieval", start, 0, 2100, 70),
            _assistant_call("retry_search", start, 6, 2300, 70),
            _assistant_call("retry_search_again", start, 12, 2400, 70),
        ],
        error_messages=["recursion limit (4) reached before producing an answer"],
    )


def _follow_up_run(now: datetime) -> AgentRun:
    """A follow-up answered from conversation context — no retrieval at all."""
    start = now - timedelta(seconds=40)
    return AgentRun(
        run_id=f"assistant-followup-{_BATCH}",
        name="kb-assistant",
        session_id=SESSION_ID,
        user_id=USER,
        input_text="So I need to be an admin to do the SSO reset?",
        output_text=(
            "Confirmed and nudged further: yes — and asked whether they already have the admin role."
        ),
        start_time=start,
        end_time=start + timedelta(seconds=4),
        llm_calls=[_assistant_call("answer_from_context", start, 0, 1900, 340)],
    )


def main() -> None:
    """Stream the assistant's runs to the live server, one per second."""
    now = datetime.now(timezone.utc)
    runs = [
        _simple_question_run(now),
        _fallback_chain_run(now),
        _recursion_limit_run(now),
        _follow_up_run(now),
    ]
    for run in runs:
        delivered = post_run(ENDPOINT, {"version": WIRE_VERSION, "run": run_to_dict(run)})
        state = "delivered" if delivered else "FAILED (is `agent-panorama serve` running?)"
        print(f"{run.run_id}: {state}")
        time.sleep(1)


if __name__ == "__main__":
    main()
