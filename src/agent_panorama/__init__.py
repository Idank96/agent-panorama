"""agent-panorama: human-readable Agent Activity Reports from LLM traces.

Public API:
    >>> from agent_panorama import generate_report
    >>> report = generate_report("traces.json", output_dir="./report", formats=["html"])
"""

from __future__ import annotations

from .analysis import build_report, rebuild_feed
from .config import ReportConfig, load_config
from .core import (
    build_report_from_file,
    build_report_from_inputs,
    generate_report,
    load_runs,
)
from .export import serialize_report
from .models import (
    AgentRollup,
    AgentRun,
    DecisionLogEntry,
    FeedItem,
    LLMCall,
    Outcome,
    Report,
    ToolCall,
)
from .render import render

__version__ = "0.2.0"

__all__ = [
    "generate_report",
    "build_report_from_file",
    "build_report_from_inputs",
    "load_runs",
    "build_report",
    "rebuild_feed",
    "render",
    "serialize_report",
    "load_config",
    "ReportConfig",
    "Report",
    "AgentRun",
    "ToolCall",
    "LLMCall",
    "DecisionLogEntry",
    "FeedItem",
    "AgentRollup",
    "Outcome",
    "__version__",
]
