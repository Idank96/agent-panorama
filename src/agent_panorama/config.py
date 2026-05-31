"""Report configuration: tool naming, escalation rules, and anomaly thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


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
    )
