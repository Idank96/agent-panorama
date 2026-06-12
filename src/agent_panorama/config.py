"""Report configuration: tool naming, escalation rules, and anomaly thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .layers.value.context import ValueContext
from .layers.value.judge import DEFAULT_JUDGE_MODEL


@dataclass
class ValueLayerConfig:
    """Configuration for the value layer (LLM-as-judge), opt-in by presence.

    The layer runs only when a ``value:`` block exists in the YAML config —
    mirroring how ``model_prices`` opts into cost estimation. ``contexts``
    holds per-agent value definitions keyed by ``agent_key`` (the slugified
    agent name), each merged field-wise over ``default``.
    """

    judge_model: str = DEFAULT_JUDGE_MODEL
    max_judgments: int = 50
    include_single_runs: bool = True
    default: ValueContext | None = None
    contexts: dict[str, ValueContext] = field(default_factory=dict)

    def context_for(self, agent_key: str) -> ValueContext | None:
        """Resolve the value context for one agent.

        Args:
            agent_key: The agent's slugified name.

        Returns:
            The agent's context merged over the default, the default alone,
            or None when neither is configured (generic rubric).
        """
        override = self.contexts.get(agent_key)
        if override is None:
            return self.default
        return override.merged_over(self.default)


@dataclass
class AnomalyThresholds:
    """Cut-offs that decide when a run is flagged as anomalous."""

    max_retries: int = 2
    max_latency_seconds: float = 30.0
    max_tool_calls: int = 15


@dataclass
class ReportConfig:
    """User-tunable configuration for report generation.

    All fields are optional; sensible defaults make the tool work with zero
    configuration while still allowing full business-language customization.
    """

    tool_descriptions: dict[str, str] = field(default_factory=dict)
    consequential_tools: list[str] = field(default_factory=list)
    escalation_tools: list[str] = field(
        default_factory=lambda: ["human_handoff", "handoff_to_agent"]
    )
    anomaly_thresholds: AnomalyThresholds = field(default_factory=AnomalyThresholds)
    detail: str = "standard"
    summarize_model: str = "google_genai:gemini-2.5-flash-lite"
    model_prices: dict[str, dict] = field(default_factory=dict)
    value: ValueLayerConfig | None = None

    def price_for(self, model: str) -> dict | None:
        """Return USD-per-1M-token prices for a model, by substring match.

        Args:
            model: The raw model name from a trace.

        Returns:
            The matching ``{"input": ..., "output": ...}`` mapping, choosing the
            longest matching substring key when several match, or None when no
            key matches (or no prices are configured).
        """
        if not model or not self.model_prices:
            return None
        matches = [(key, price) for key, price in self.model_prices.items() if key in model]
        if not matches:
            return None
        return max(matches, key=lambda item: len(item[0]))[1]

    def describe_tool(self, tool_name: str) -> str:
        """Return the business-readable description for a tool name.

        Args:
            tool_name: The raw tool name from the trace.

        Returns:
            The configured description, or a humanized version of the name.
        """
        if tool_name in self.tool_descriptions:
            return self.tool_descriptions[tool_name]
        return tool_name.replace("_", " ").strip().capitalize()

    def is_consequential(self, tool_name: str) -> bool:
        """Whether a tool call should appear in the decision log.

        Args:
            tool_name: The raw tool name from the trace.

        Returns:
            True if the tool is consequential. When no allow-list is
            configured, every tool call is treated as consequential.
        """
        if not self.consequential_tools:
            return True
        return tool_name in self.consequential_tools

    def is_escalation(self, tool_name: str) -> bool:
        """Whether a tool call represents a human escalation."""
        return tool_name in self.escalation_tools


def load_config(path: str | Path | None) -> ReportConfig:
    """Load a :class:`ReportConfig` from a YAML file.

    Args:
        path: Path to a YAML config file, or None for all defaults.

    Returns:
        A populated :class:`ReportConfig`.
    """
    if path is None:
        return ReportConfig()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return _config_from_dict(raw)


def _config_from_dict(raw: dict) -> ReportConfig:
    """Build a :class:`ReportConfig` from a parsed YAML mapping."""
    thresholds = AnomalyThresholds(**(raw.get("anomaly_thresholds") or {}))
    return ReportConfig(
        tool_descriptions=raw.get("tool_descriptions") or {},
        consequential_tools=raw.get("consequential_tools") or [],
        escalation_tools=raw.get("escalation_tools") or ["human_handoff", "handoff_to_agent"],
        anomaly_thresholds=thresholds,
        detail=str(raw.get("detail") or "standard"),
        summarize_model=str(raw.get("summarize_model") or "google_genai:gemini-2.5-flash-lite"),
        model_prices=raw.get("model_prices") or {},
        value=_value_config_from_dict(raw.get("value")),
    )


def _value_config_from_dict(raw: dict | None) -> ValueLayerConfig | None:
    """Build a :class:`ValueLayerConfig` from the ``value:`` YAML block."""
    if not raw:
        return None
    contexts = {
        str(key): _context_from_dict(entry) or ValueContext()
        for key, entry in (raw.get("contexts") or {}).items()
    }
    return ValueLayerConfig(
        judge_model=str(raw.get("judge_model") or DEFAULT_JUDGE_MODEL),
        max_judgments=int(raw.get("max_judgments") or 50),
        include_single_runs=bool(raw.get("include_single_runs", True)),
        default=_context_from_dict(raw.get("default")),
        contexts=contexts,
    )


def _context_from_dict(raw: dict | None) -> ValueContext | None:
    """Build a :class:`ValueContext` from one YAML context mapping."""
    if not raw:
        return None
    return ValueContext(
        domain=raw.get("domain"),
        user_goal=raw.get("user_goal"),
        success_criteria=[str(item) for item in raw.get("success_criteria") or []],
        custom_dimensions={
            str(key): str(val) for key, val in (raw.get("custom_dimensions") or {}).items()
        },
    )


def value_config_from_dict(raw: dict | None) -> ValueLayerConfig | None:
    """Public entry point to build a :class:`ValueLayerConfig` from a mapping.

    Args:
        raw: A ``value:``-shaped mapping, or None.

    Returns:
        The parsed config, or None when ``raw`` is empty.
    """
    return _value_config_from_dict(raw)


def value_config_to_dict(config: ValueLayerConfig | None) -> dict:
    """Serialize a :class:`ValueLayerConfig` back to its ``value:`` mapping.

    The inverse of :func:`value_config_from_dict`, used to persist the value
    definition the manager edits in the dashboard.

    Args:
        config: The value-layer config, or None.

    Returns:
        A JSON/YAML-ready mapping; empty when ``config`` is None.
    """
    if config is None:
        return {}
    return {
        "judge_model": config.judge_model,
        "max_judgments": config.max_judgments,
        "include_single_runs": config.include_single_runs,
        "default": _context_to_dict(config.default),
        "contexts": {key: _context_to_dict(ctx) for key, ctx in config.contexts.items()},
    }


def _context_to_dict(context: ValueContext | None) -> dict | None:
    """Serialize one :class:`ValueContext`, or None when unset."""
    if context is None:
        return None
    return {
        "domain": context.domain,
        "user_goal": context.user_goal,
        "success_criteria": list(context.success_criteria),
        "custom_dimensions": dict(context.custom_dimensions),
    }


def value_config_is_empty(config: ValueLayerConfig | None) -> bool:
    """Whether a value config carries no definition (so the layer stays off)."""
    if config is None:
        return True
    return config.default is None and not config.contexts
