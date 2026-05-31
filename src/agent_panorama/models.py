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
class Step:
    """One meaningful unit of work in an agent run (a graph node or tool call).

    Steps form the run's narrative timeline. A ``node`` step is a framework graph
    node (e.g. a LangGraph node), a ``tool`` step is a tool execution, and a
    ``model`` step is model work with no enclosing node. Counts aggregate the
    activity that happened *inside* the step's subtree.
    """

    name: str
    kind: str = "node"
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: str = "success"
    error: str | None = None
    model_calls: int = 0
    tool_calls: int = 0
    tokens: int = 0

    @property
    def succeeded(self) -> bool:
        """Whether the step completed without an error."""
        return self.status == "success" and self.error is None

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration of the step in seconds, if both times are known."""
        if self.start_time is None or self.end_time is None:
            return None
        return max(0.0, (self.end_time - self.start_time).total_seconds())


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
    result_summary: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    outcome: Outcome = Outcome.UNKNOWN
    steps: list[Step] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    llm_calls: list[LLMCall] = field(default_factory=list)
    retry_count: int = 0
    fallback_used: bool = False
    error_messages: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    cost_usd: float | None = None

    @property
    def action_count(self) -> int:
        """Number of narrative steps the run took (falls back to tool calls)."""
        return len(self.steps) or len(self.tool_calls)

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
class FeedItem:
    """One cross-agent activity-feed entry, derived from a single run."""

    run_id: str
    agent_name: str
    agent_key: str
    action: str
    outcome: Outcome
    timestamp: datetime | None
    retry_count: int
    anomaly_count: int
    tokens: int
    cost_usd: float | None
    summary: str
    facts: list[tuple[str, str]] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)


@dataclass
class AgentRollup:
    """Aggregated per-agent activity across all runs of one agent."""

    agent_name: str
    agent_key: str
    runs: int
    actions: int
    success_rate: float
    escalation_rate: float
    failure_rate: float
    retry_rate: float
    total_tokens: int
    total_cost_usd: float | None


@dataclass
class Report:
    """The full report payload handed to the templates."""

    runs: list[AgentRun]
    decision_log: list[DecisionLogEntry]
    feed: list[FeedItem] = field(default_factory=list)
    rollups: list[AgentRollup] = field(default_factory=list)
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
    def total_steps(self) -> int:
        """Number of narrative steps across all runs."""
        return sum(run.action_count for run in self.runs)

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
    def total_cost_usd(self) -> float | None:
        """Total estimated USD cost, or None when no run has a cost."""
        costs = [run.cost_usd for run in self.runs if run.cost_usd is not None]
        return sum(costs) if costs else None

    @property
    def all_anomalies(self) -> list[tuple[str, str]]:
        """Flat list of (agent_name, anomaly_description) for every run."""
        return [(run.name, note) for run in self.runs for note in run.anomalies]
