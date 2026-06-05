"""Post a few synthetic agent runs to a running live dashboard.

Usage (two terminals):

    # terminal 1 — start the dashboard (needs the 'live' extra)
    agent-panorama serve --open

    # terminal 2 — stream sample runs into it (stdlib only, no extras)
    python examples/live_demo.py

Each run appears in the dashboard within one poll tick (~3 seconds).
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_panorama.live.serde import WIRE_VERSION, run_to_dict
from agent_panorama.live.transport import post_run
from agent_panorama.models import AgentRun, LLMCall, ToolCall

ENDPOINT = "http://localhost:8321/api/runs"

# The server is idempotent on run_id (re-posting the same id replaces the run),
# so each demo execution gets fresh ids — re-running adds new feed entries.
_BATCH = uuid.uuid4().hex[:8]


def _sample_runs(now: datetime) -> list[AgentRun]:
    """Build a small fleet of generic, obviously-synthetic runs."""
    return [
        AgentRun(
            run_id=f"demo-research-{_BATCH}",
            name="research-assistant",
            input_text="Summarize this week's solar-panel efficiency papers.",
            output_text="Summarized 12 papers; perovskite cells lead at 26.1%.",
            start_time=now - timedelta(minutes=4),
            end_time=now - timedelta(minutes=3),
            tool_calls=[
                ToolCall(name="web_search", arguments={"query": "solar panel efficiency 2026"}),
                ToolCall(name="web_search", arguments={"query": "perovskite cell records"}),
            ],
            llm_calls=[
                LLMCall(name="chat", model="gpt-4o-mini", input_tokens=2100, output_tokens=430)
            ],
        ),
        AgentRun(
            run_id=f"demo-weather-{_BATCH}",
            name="travel-planner",
            input_text="What's the weather for the Lisbon offsite?",
            output_text="Sunny all week, 24-27°C; no schedule changes needed.",
            start_time=now - timedelta(minutes=2),
            end_time=now - timedelta(minutes=2, seconds=-20),
            tool_calls=[ToolCall(name="get_weather", arguments={"city": "Lisbon"})],
            llm_calls=[
                LLMCall(name="chat", model="gpt-4o-mini", input_tokens=800, output_tokens=120)
            ],
        ),
        AgentRun(
            run_id=f"demo-email-{_BATCH}",
            name="inbox-assistant",
            input_text="Send the weekly status email to the team.",
            output_text="",
            start_time=now - timedelta(minutes=1),
            end_time=now,
            tool_calls=[
                ToolCall(
                    name="send_email",
                    arguments={"to": "team@example.com"},
                    status="error",
                    error="SMTP timeout",
                )
            ],
            error_messages=["SMTP timeout after 3 attempts"],
        ),
    ]


def main() -> None:
    """Stream the sample runs to the live server, one per second."""
    runs = _sample_runs(datetime.now(timezone.utc))
    for run in runs:
        delivered = post_run(ENDPOINT, {"version": WIRE_VERSION, "run": run_to_dict(run)})
        state = "delivered" if delivered else "FAILED (is `agent-panorama serve` running?)"
        print(f"{run.name}: {state}")
        time.sleep(1)


if __name__ == "__main__":
    main()
