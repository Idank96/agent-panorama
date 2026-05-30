"""agent-panorama: human-readable Agent Activity Reports from LLM traces.

Public API:
    >>> from agent_panorama import generate_report
    >>> report = generate_report("traces.json", output_dir="./report", formats=["html"])
"""

from __future__ import annotations

from .analysis import build_report
from .config import ReportConfig, load_config
from .core import build_report_from_file, generate_report
from .models import AgentRun, DecisionLogEntry, LLMCall, Outcome, Report, ToolCall
from .render import render

__version__ = "0.1.0"

__all__ = [
    "generate_report",
    "build_report_from_file",
    "build_report",
    "render",
    "load_config",
    "ReportConfig",
    "Report",
    "AgentRun",
    "ToolCall",
    "LLMCall",
    "DecisionLogEntry",
    "Outcome",
    "__version__",
]
