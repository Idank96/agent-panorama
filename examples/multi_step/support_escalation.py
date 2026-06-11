"""Live demo: a scheduled review pipeline with an escalation ladder (support style).

Imitates the trace *shape* of a daily pipeline that reviews many support ticket
queues with one big reasoning LLM call each, then acts on the result:

- **Healthy ticket**: fetch ticket -> analyze -> log status (success).
- **Quiet ticket**: analysis says "needs attention" -> send a reminder.
- **Day-7 silent ticket**: the escalation ladder tops out -> hand off to a
  human (`human_handoff`), which the dashboard shows as escalated.
- **Flaky LLM**: the analyzer call errors once and is retried (retry signal).
- **Flaky messaging API**: three failed posts then a success — the same tool
  failing and later succeeding flags both retries and a recovered fallback,
  and >2 retries trips the anomaly threshold.
- **Dead ticket**: the fetch itself fails with no recovery (failed run).

Usage (two terminals):

    agent-panorama serve --open
    python examples/multi_step/support_escalation.py
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

ANALYZER_MODEL = "claude-sonnet-4-5"


def _fetch(start: datetime, messages: int) -> ToolCall:
    """A ticket-fetch tool call."""
    return ToolCall(
        name="fetch_ticket",
        arguments={"limit": 100},
        output=f"{messages} messages over the last 14 days",
        timestamp=start + timedelta(seconds=1),
        latency_ms=700.0,
    )


def _analyze(start: datetime, *, offset: int = 2) -> LLMCall:
    """The big single-call analyzer (long context, structured JSON out)."""
    return LLMCall(
        name="analyze_ticket",
        model=ANALYZER_MODEL,
        input_tokens=4800,
        output_tokens=850,
        timestamp=start + timedelta(seconds=offset),
        latency_ms=9500.0,
    )


def _healthy_run(now: datetime) -> AgentRun:
    """A ticket that's on track: analyze and log, nothing else."""
    start = now - timedelta(minutes=8)
    return AgentRun(
        run_id=f"pipeline-healthy-{_BATCH}",
        name="ticket-tracker",
        input_text="Daily review: ticket #tickets-alpha",
        output_text="On track: customer shared logs yesterday, next reply booked.",
        start_time=start,
        end_time=start + timedelta(seconds=14),
        tool_calls=[
            _fetch(start, 86),
            ToolCall(
                name="log_status",
                arguments={"status": "on-track", "phase": "working-on-fix"},
                output="tracker row updated",
                timestamp=start + timedelta(seconds=12),
                latency_ms=600.0,
            ),
        ],
        llm_calls=[_analyze(start)],
    )


def _reminder_run(now: datetime) -> AgentRun:
    """A quiet ticket: first rung of the escalation ladder (a reminder)."""
    start = now - timedelta(minutes=6, seconds=30)
    return AgentRun(
        run_id=f"pipeline-reminder-{_BATCH}",
        name="ticket-tracker",
        input_text="Daily review: ticket #tickets-bravo",
        output_text="Customer silent for 3 days; sent the first friendly reminder.",
        start_time=start,
        end_time=start + timedelta(seconds=16),
        tool_calls=[
            _fetch(start, 41),
            ToolCall(
                name="send_reminder",
                arguments={"rung": 1, "silent_days": 3},
                output="reminder posted to the ticket",
                timestamp=start + timedelta(seconds=13),
                latency_ms=800.0,
            ),
            ToolCall(
                name="log_status",
                arguments={"status": "silent", "phase": "working-on-fix"},
                output="tracker row updated",
                timestamp=start + timedelta(seconds=15),
                latency_ms=550.0,
            ),
        ],
        llm_calls=[_analyze(start)],
    )


def _escalation_run(now: datetime) -> AgentRun:
    """Day-7 silence: the ladder tops out and a human takes over."""
    start = now - timedelta(minutes=5)
    return AgentRun(
        run_id=f"pipeline-escalate-{_BATCH}",
        name="ticket-tracker",
        input_text="Daily review: ticket #tickets-charlie",
        output_text="Silent for 7 days after two reminders; escalated to the support lead.",
        start_time=start,
        end_time=start + timedelta(seconds=15),
        tool_calls=[
            _fetch(start, 19),
            ToolCall(
                name="human_handoff",
                arguments={"reason": "7 days silent after 2 reminders"},
                output="alert posted to the support-lead channel",
                timestamp=start + timedelta(seconds=13),
                latency_ms=750.0,
            ),
        ],
        llm_calls=[_analyze(start)],
    )


def _flaky_llm_run(now: datetime) -> AgentRun:
    """The analyzer errors once and is retried — a recovered run with 1 retry."""
    start = now - timedelta(minutes=3, seconds=30)
    failed = LLMCall(
        name="analyze_ticket",
        model=ANALYZER_MODEL,
        input_tokens=4700,
        output_tokens=0,
        timestamp=start + timedelta(seconds=2),
        latency_ms=4000.0,
        status="error",
        error="model timeout after 4s",
    )
    return AgentRun(
        run_id=f"pipeline-flaky-llm-{_BATCH}",
        name="ticket-tracker",
        input_text="Daily review: ticket #tickets-delta",
        output_text="On track after retry: customer confirmed the fix resolved it.",
        start_time=start,
        end_time=start + timedelta(seconds=26),
        tool_calls=[
            _fetch(start, 64),
            ToolCall(
                name="trigger_code_review",
                arguments={"repo": "proposed-fix"},
                output="review workflow queued",
                timestamp=start + timedelta(seconds=23),
                latency_ms=900.0,
            ),
        ],
        llm_calls=[failed, _analyze(start, offset=8)],
    )


def _flaky_messaging_run(now: datetime) -> AgentRun:
    """Three failed posts, then success: retries + recovery + anomaly."""
    start = now - timedelta(minutes=2)
    failures = [
        ToolCall(
            name="send_reminder",
            arguments={"rung": 2, "attempt": attempt},
            timestamp=start + timedelta(seconds=12 + attempt * 3),
            latency_ms=2000.0,
            status="error",
            error="messaging API 429: rate limited",
        )
        for attempt in (1, 2, 3)
    ]
    return AgentRun(
        run_id=f"pipeline-flaky-msg-{_BATCH}",
        name="ticket-tracker",
        input_text="Daily review: ticket #tickets-echo",
        output_text="Second reminder delivered after rate-limit retries.",
        start_time=start,
        end_time=start + timedelta(seconds=30),
        tool_calls=[
            _fetch(start, 38),
            *failures,
            ToolCall(
                name="send_reminder",
                arguments={"rung": 2, "attempt": 4},
                output="reminder posted to the ticket",
                timestamp=start + timedelta(seconds=24),
                latency_ms=900.0,
            ),
        ],
        llm_calls=[_analyze(start)],
    )


def _dead_ticket_run(now: datetime) -> AgentRun:
    """The fetch fails outright and nothing recovers — a failed run."""
    start = now - timedelta(seconds=45)
    return AgentRun(
        run_id=f"pipeline-dead-{_BATCH}",
        name="ticket-tracker",
        input_text="Daily review: ticket #tickets-foxtrot",
        output_text="",
        start_time=start,
        end_time=start + timedelta(seconds=6),
        tool_calls=[
            ToolCall(
                name="fetch_ticket",
                arguments={"limit": 100},
                timestamp=start + timedelta(seconds=1),
                latency_ms=5000.0,
                status="error",
                error="ticket_not_found: bot lost access to the ticket",
            )
        ],
        error_messages=["ticket_not_found: bot lost access to the ticket"],
    )


def main() -> None:
    """Stream the pipeline's runs to the live server, one per second."""
    now = datetime.now(timezone.utc)
    runs = [
        _healthy_run(now),
        _reminder_run(now),
        _escalation_run(now),
        _flaky_llm_run(now),
        _flaky_messaging_run(now),
        _dead_ticket_run(now),
    ]
    for run in runs:
        delivered = post_run(ENDPOINT, {"version": WIRE_VERSION, "run": run_to_dict(run)})
        state = "delivered" if delivered else "FAILED (is `agent-panorama serve` running?)"
        print(f"{run.input_text.split(': ')[-1]}: {state}")
        time.sleep(1)


if __name__ == "__main__":
    main()
