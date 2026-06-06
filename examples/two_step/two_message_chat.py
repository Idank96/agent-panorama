"""Two steps: two messages in the same chat, one after the other.

Both turns share one ``(session_id, user_id)``, so the dashboard shows a
SINGLE card that updates as the second message lands — "Interactions: 2"
— instead of two separate lines.

Usage (two terminals):

    agent-panorama serve --open
    python examples/two_step/two_message_chat.py
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

SESSION_ID = f"trip-chat-{_BATCH}"
TRAVELER = "traveler-noa"


def _first_turn(now: datetime) -> AgentRun:
    """Turn 1: find a flight."""
    start = now - timedelta(minutes=2)
    return AgentRun(
        run_id=f"two-step-turn1-{_BATCH}",
        name="travel-planner",
        session_id=SESSION_ID,
        user_id=TRAVELER,
        input_text="Find me a morning flight to Lisbon next Friday.",
        output_text="Found three morning options; the 7:40 direct flight is the cheapest.",
        start_time=start,
        end_time=start + timedelta(seconds=8),
        tool_calls=[
            ToolCall(
                name="search_flights",
                arguments={
                    "destination": "Lisbon",
                    "date": "next Friday",
                    "part_of_day": "morning",
                },
                output="3 results; best: 07:40 direct",
                timestamp=start + timedelta(seconds=2),
                latency_ms=1900.0,
            )
        ],
        llm_calls=[
            LLMCall(
                name="answer",
                model="claude-haiku-4-5",
                input_tokens=700,
                output_tokens=160,
                timestamp=start,
                latency_ms=1200.0,
            )
        ],
    )


def _second_turn(now: datetime) -> AgentRun:
    """Turn 2: follow-up in the same conversation."""
    start = now - timedelta(seconds=30)
    return AgentRun(
        run_id=f"two-step-turn2-{_BATCH}",
        name="travel-planner",
        session_id=SESSION_ID,
        user_id=TRAVELER,
        input_text="Great — and a hotel near the old town for two nights?",
        output_text="Suggested two well-rated hotels in Alfama within the budget.",
        start_time=start,
        end_time=start + timedelta(seconds=7),
        tool_calls=[
            ToolCall(
                name="search_hotels",
                arguments={"area": "old town", "nights": 2},
                output="2 options near Alfama",
                timestamp=start + timedelta(seconds=2),
                latency_ms=1700.0,
            )
        ],
        llm_calls=[
            LLMCall(
                name="answer",
                model="claude-haiku-4-5",
                input_tokens=900,
                output_tokens=140,
                timestamp=start,
                latency_ms=1100.0,
            )
        ],
    )


def main() -> None:
    """Post both turns; watch the single card update between them."""
    now = datetime.now(timezone.utc)
    for run in (_first_turn(now), _second_turn(now)):
        delivered = post_run(ENDPOINT, {"version": WIRE_VERSION, "run": run_to_dict(run)})
        state = "delivered" if delivered else "FAILED (is `agent-panorama serve` running?)"
        print(f"{run.run_id}: {state}")
        time.sleep(4)


if __name__ == "__main__":
    main()
