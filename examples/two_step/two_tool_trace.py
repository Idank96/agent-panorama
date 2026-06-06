"""Two steps: one agent run that executes two tool calls, ending in one trace.

The LangGraph equivalent of two nodes (research → notify) inside a single
invocation: the run is ONE trace and ONE feed card, whose details show both
steps.

Usage (two terminals):

    agent-panorama serve --open
    python examples/two_step/two_tool_trace.py
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
    """One request → search the web → email the digest → one answer."""
    start = now - timedelta(seconds=45)
    return AgentRun(
        run_id=f"two-step-tools-{_BATCH}",
        name="research-assistant",
        input_text="Find today's top robotics news and email me a digest.",
        output_text="Emailed a digest of the three biggest robotics stories from today.",
        start_time=start,
        end_time=start + timedelta(seconds=18),
        tool_calls=[
            ToolCall(
                name="web_search",
                arguments={"query": "robotics news today"},
                output="3 relevant articles found",
                timestamp=start + timedelta(seconds=2),
                latency_ms=2400.0,
            ),
            ToolCall(
                name="send_email",
                arguments={"to": "user@example.com", "subject": "Robotics digest"},
                output="email sent",
                timestamp=start + timedelta(seconds=12),
                latency_ms=900.0,
            ),
        ],
        llm_calls=[
            LLMCall(
                name="plan_search",
                model="claude-haiku-4-5",
                input_tokens=500,
                output_tokens=70,
                timestamp=start,
                latency_ms=900.0,
            ),
            LLMCall(
                name="write_digest",
                model="claude-haiku-4-5",
                input_tokens=1600,
                output_tokens=380,
                timestamp=start + timedelta(seconds=6),
                latency_ms=2600.0,
            ),
        ],
    )


def main() -> None:
    """Post the single two-tool run to the live server."""
    run = _run(datetime.now(timezone.utc))
    delivered = post_run(ENDPOINT, {"version": WIRE_VERSION, "run": run_to_dict(run)})
    state = "delivered" if delivered else "FAILED (is `agent-panorama serve` running?)"
    print(f"{run.name}: {state}")


if __name__ == "__main__":
    main()
