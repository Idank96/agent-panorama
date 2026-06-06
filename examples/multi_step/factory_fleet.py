"""Live demo: an orchestrator + sub-agents fleet (manufacturing-planning style).

Imitates the trace *shape* of a two-level agent system:

- A cheap **orchestrator** model routes each request to a specialized sub-agent
  via a ``call_<domain>_agent`` tool (one LLM call, one routing tool call).
- **Sub-agents** run a heavier model through multi-step tool sequences,
  including a long-polling tool (submit job -> poll status until terminal),
  which shows up as one slow tool call and a >30s run (latency anomaly).
- A composite **health-check tool** aggregates several internal probes but
  appears as a single tool call.
- A destructive action goes through **human approval** (`human_handoff`),
  which the dashboard surfaces as an escalated run.

Usage (two terminals):

    agent-panorama serve --open
    python examples/multi_step/factory_fleet.py
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

ROUTER_MODEL = "claude-haiku-4-5"
WORKER_MODEL = "claude-sonnet-4-6"


def _orchestrator_run(now: datetime) -> AgentRun:
    """The routing layer: one small LLM call, one sub-agent dispatch tool."""
    start = now - timedelta(minutes=6)
    return AgentRun(
        run_id=f"fleet-orchestrator-{_BATCH}",
        name="plant-operations-agent",
        input_text="Schedule all jobs due this week into next week.",
        output_text="Routed to the scheduling agent; its answer streams to the user.",
        start_time=start,
        end_time=start + timedelta(seconds=3),
        tool_calls=[
            ToolCall(
                name="call_scheduling_agent",
                arguments={"request": "Schedule all jobs due this week into next week."},
                output="delegated (response streamed directly to the user)",
                timestamp=start + timedelta(seconds=1),
                latency_ms=1800.0,
            )
        ],
        llm_calls=[
            LLMCall(
                name="route_request",
                model=ROUTER_MODEL,
                input_tokens=240,
                output_tokens=60,
                timestamp=start,
                latency_ms=900.0,
            )
        ],
    )


def _scheduling_run(now: datetime) -> AgentRun:
    """The heavy sub-agent: fetch -> long-polling schedule -> failure analysis."""
    start = now - timedelta(minutes=5, seconds=30)
    return AgentRun(
        run_id=f"fleet-scheduling-{_BATCH}",
        name="scheduling-agent",
        input_text="Schedule all jobs due this week into next week.",
        output_text=(
            "Scheduled 45 of 47 jobs for next week. 2 could not be placed: one task "
            "already started, one station lacks capacity on Tuesday."
        ),
        start_time=start,
        end_time=start + timedelta(seconds=65),
        tool_calls=[
            ToolCall(
                name="get_work_items",
                arguments={"due_within_days": 7},
                output="47 work items with task trees",
                timestamp=start + timedelta(seconds=2),
                latency_ms=850.0,
            ),
            ToolCall(
                name="schedule_jobs",
                arguments={"task_count": 47, "window": "next week"},
                output="COMPLETED: scheduled=45 unassigned=2 (polled status for 42s)",
                timestamp=start + timedelta(seconds=6),
                latency_ms=42000.0,
            ),
            ToolCall(
                name="get_schedule_failures",
                arguments={"job_id": "job-demo"},
                output="2 failures: task already started; insufficient station capacity",
                timestamp=start + timedelta(seconds=50),
                latency_ms=9000.0,
            ),
        ],
        llm_calls=[
            LLMCall(
                name="plan_fetch",
                model=WORKER_MODEL,
                input_tokens=600,
                output_tokens=90,
                timestamp=start,
                latency_ms=1100.0,
            ),
            LLMCall(
                name="plan_schedule",
                model=WORKER_MODEL,
                input_tokens=1400,
                output_tokens=120,
                timestamp=start + timedelta(seconds=4),
                latency_ms=1300.0,
            ),
            LLMCall(
                name="inspect_failures",
                model=WORKER_MODEL,
                input_tokens=900,
                output_tokens=80,
                timestamp=start + timedelta(seconds=49),
                latency_ms=1000.0,
            ),
            LLMCall(
                name="final_answer",
                model=WORKER_MODEL,
                input_tokens=1100,
                output_tokens=260,
                timestamp=start + timedelta(seconds=60),
                latency_ms=2400.0,
            ),
        ],
    )


def _health_check_run(now: datetime) -> AgentRun:
    """A composite tool: several internal probes behind one tool call."""
    start = now - timedelta(minutes=3)
    return AgentRun(
        run_id=f"fleet-health-{_BATCH}",
        name="plant-operations-agent",
        input_text="How is production health right now?",
        output_text=(
            "All clear: scheduler idle, 3 open warnings, no overdue jobs, station capacity at 71%."
        ),
        start_time=start,
        end_time=start + timedelta(seconds=11),
        tool_calls=[
            ToolCall(
                name="run_production_health_check",
                arguments={},
                output="aggregated 4 probes: alerts, scheduler state, overdue jobs, capacity",
                timestamp=start + timedelta(seconds=1),
                latency_ms=6200.0,
            )
        ],
        llm_calls=[
            LLMCall(
                name="route_request",
                model=ROUTER_MODEL,
                input_tokens=230,
                output_tokens=55,
                timestamp=start,
                latency_ms=850.0,
            ),
            LLMCall(
                name="summarize_health",
                model=ROUTER_MODEL,
                input_tokens=700,
                output_tokens=160,
                timestamp=start + timedelta(seconds=8),
                latency_ms=1500.0,
            ),
        ],
    )


def _approval_run(now: datetime) -> AgentRun:
    """A destructive action gated by human approval (escalated outcome)."""
    start = now - timedelta(minutes=1, seconds=30)
    return AgentRun(
        run_id=f"fleet-approval-{_BATCH}",
        name="maintenance-agent",
        input_text="Cancel job J-1042, the mold cracked.",
        output_text="Cancellation needs a human sign-off; handed the decision to the operator.",
        start_time=start,
        end_time=start + timedelta(seconds=8),
        tool_calls=[
            ToolCall(
                name="human_handoff",
                arguments={"action": "cancel_job", "job_id": "J-1042"},
                output="approval requested from the floor operator",
                timestamp=start + timedelta(seconds=3),
                latency_ms=400.0,
            )
        ],
        llm_calls=[
            LLMCall(
                name="assess_request",
                model=WORKER_MODEL,
                input_tokens=480,
                output_tokens=110,
                timestamp=start,
                latency_ms=1200.0,
            )
        ],
    )


def main() -> None:
    """Stream the fleet's runs to the live server, one per second."""
    now = datetime.now(timezone.utc)
    runs = [
        _orchestrator_run(now),
        _scheduling_run(now),
        _health_check_run(now),
        _approval_run(now),
    ]
    for run in runs:
        delivered = post_run(ENDPOINT, {"version": WIRE_VERSION, "run": run_to_dict(run)})
        state = "delivered" if delivered else "FAILED (is `agent-panorama serve` running?)"
        print(f"{run.name}: {state}")
        time.sleep(1)


if __name__ == "__main__":
    main()
