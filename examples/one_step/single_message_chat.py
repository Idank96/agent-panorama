"""One step: a chat with exactly one message.

The run carries a ``(session_id, user_id)``, so the dashboard treats it as a
session — still one card (one turn so far), but with a stable identity: if the
same user sends another message later with the same session id, the card
updates in place instead of adding a new line.

Usage (two terminals):

    agent-panorama serve --open
    python examples/one_step/single_message_chat.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_panorama.live.serde import WIRE_VERSION, run_to_dict
from agent_panorama.live.transport import post_run
from agent_panorama.models import AgentRun, LLMCall

ENDPOINT = "http://localhost:8321/api/runs"
_BATCH = uuid.uuid4().hex[:8]


def _run(now: datetime) -> AgentRun:
    """One chat message, answered from the model alone (no tools)."""
    start = now - timedelta(seconds=15)
    return AgentRun(
        run_id=f"one-step-chat-{_BATCH}",
        name="support-assistant",
        session_id=f"chat-{_BATCH}",
        user_id="customer-dana",
        input_text="How do I reset my password?",
        output_text="Walked the customer through the password reset flow from the login page.",
        start_time=start,
        end_time=start + timedelta(seconds=4),
        llm_calls=[
            LLMCall(
                name="answer",
                model="claude-haiku-4-5",
                input_tokens=420,
                output_tokens=110,
                timestamp=start,
                latency_ms=1100.0,
            )
        ],
    )


def main() -> None:
    """Post the single chat turn to the live server."""
    run = _run(datetime.now(timezone.utc))
    delivered = post_run(ENDPOINT, {"version": WIRE_VERSION, "run": run_to_dict(run)})
    state = "delivered" if delivered else "FAILED (is `agent-panorama serve` running?)"
    print(f"{run.name}: {state}")


if __name__ == "__main__":
    main()
