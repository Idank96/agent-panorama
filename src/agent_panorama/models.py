"""Normalized data models shared across parsers, analysis, and reporting.

These dataclasses are deliberately framework-agnostic: every parser (Langfuse,
LangSmith, ...) maps its raw export into this single shape so that analysis and
rendering never need to know where the data came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Outcome(str, Enum):
    """Final result of an agent run, in business terms."""

    SUCCESS = "success"
    FAILURE = "failure"
    ESCALATED = "human-escalated"
    UNKNOWN = "unknown"


@dataclass
class ToolCall:
    """A single tool invocation made by an agent."""

    name: str
    arguments: dict
    output: object | None = None
    timestamp: datetime | None = None
    latency_ms: float | None = None
    status: str = "success"
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Whether the tool call completed without an error."""
        return self.status == "success" and self.error is None


@dataclass
class LLMCall:
    """A single model generation, with token usage."""

    name: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    timestamp: datetime | None = None
    latency_ms: float | None = None
    status: str = "success"
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        """Combined prompt and completion tokens."""
        return self.input_tokens + self.output_tokens


@dataclass
class AgentRun:
    """One agent/chain execution (a single trace), fully normalized."""

    run_id: str
    name: str
    input_text: str = ""
    output_text: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    outcome: Outcome = Outcome.UNKNOWN
    tool_calls: list[ToolCall] = field(default_factory=list)
    llm_calls: list[LLMCall] = field(default_factory=list)
    retry_count: int = 0
    fallback_used: bool = False
    error_messages: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        """Sum of prompt tokens across all model calls."""
        return sum(call.input_tokens for call in self.llm_calls)

    @property
    def total_output_tokens(self) -> int:
        """Sum of completion tokens across all model calls."""
        return sum(call.output_tokens for call in self.llm_calls)

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed by the run."""
        return self.total_input_tokens + self.total_output_tokens

    @property
    def latency_seconds(self) -> float:
        """Wall-clock duration of the run in seconds (0 if unknown)."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return max(0.0, (self.end_time - self.start_time).total_seconds())


@dataclass
class DecisionLogEntry:
    """A single consequential action for the cross-run decision log table."""

    timestamp: datetime | None
    agent_name: str
    action: str
    parameters: str
    outcome: str


@dataclass
class Report:
    """The full report payload handed to the templates."""

    runs: list[AgentRun]
    decision_log: list[DecisionLogEntry]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_runs(self) -> int:
        """Number of agent runs in the report."""
        return len(self.runs)

    @property
    def total_actions(self) -> int:
        """Number of tool calls across all runs."""
        return sum(len(run.tool_calls) for run in self.runs)

    @property
    def total_tokens(self) -> int:
        """Total tokens across all runs."""
        return sum(run.total_tokens for run in self.runs)

    @property
    def time_range(self) -> tuple[datetime | None, datetime | None]:
        """Earliest start and latest end across all runs."""
        starts = [r.start_time for r in self.runs if r.start_time]
        ends = [r.end_time for r in self.runs if r.end_time]
        return (min(starts) if starts else None, max(ends) if ends else None)

    @property
    def all_anomalies(self) -> list[tuple[str, str]]:
        """Flat list of (agent_name, anomaly_description) for every run."""
        return [(run.name, note) for run in self.runs for note in run.anomalies]
