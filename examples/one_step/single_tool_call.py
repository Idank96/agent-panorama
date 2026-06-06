"""One step: an agent answers one request with a single tool call.

The simplest possible trace — one LLM decision, one tool execution, one
answer. Shows up as one feed card with one step.

Usage (two terminals):

    agent-panorama serve --open
    python examples/one_step/single_tool_call.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_panorama.live.serde import WIRE_VERSION, run_to_dict
from agent_panorama.live.transport import post_run
from agent_panorama.models import AgentRun, LLMCall, ToolCall

ENDPOINT = "http://localhost:8321/api/runs"
_BATCH = uuid.uuid4().hex[:8]


def _run(now: datetime) -> AgentRun:
    """One request → one tool call → one answer."""
    start = now - timedelta(seconds=20)
    return AgentRun(
        run_id=f"one-step-tool-{_BATCH}",
        name="weather-assistant",
        input_text="What's the weather in Lisbon today?",
        output_text="Sunny and 26°C in Lisbon — perfect day to be outside.",
        start_time=start,
        end_time=start + timedelta(seconds=5),
        tool_calls=[
            ToolCall(
                name="get_weather",
                arguments={"city": "Lisbon"},
                output="sunny, 26°C, light breeze",
                timestamp=start + timedelta(seconds=1),
                latency_ms=600.0,
            )
        ],
        llm_calls=[
            LLMCall(
                name="answer",
                model="claude-haiku-4-5",
                input_tokens=350,
                output_tokens=60,
                timestamp=start,
                latency_ms=800.0,
            )
        ],
    )


def main() -> None:
    """Post the single run to the live server."""
    run = _run(datetime.now(timezone.utc))
    delivered = post_run(ENDPOINT, {"version": WIRE_VERSION, "run": run_to_dict(run)})
    state = "delivered" if delivered else "FAILED (is `agent-panorama serve` running?)"
    print(f"{run.name}: {state}")


if __name__ == "__main__":
    main()
