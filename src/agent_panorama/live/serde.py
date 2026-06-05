"""Versioned JSON wire format for shipping :class:`AgentRun` over HTTP.

The callback handler serializes each completed run with :func:`run_to_dict`
and POSTs it to the live server, which rebuilds the run with
:func:`run_from_dict`. Only stdlib types appear on the wire so both sides
work from a base install.
"""

from __future__ import annotations

from datetime import datetime

from ..models import AgentRun, LLMCall, Outcome, Step, ToolCall
from ..parsers.common import parse_time

WIRE_VERSION = 1


def run_to_dict(run: AgentRun) -> dict:
    """Serialize a run to a JSON-safe dict for the live wire format.

    Args:
        run: The completed run to serialize.

    Returns:
        A dict with all run fields, datetimes rendered as ISO-8601 strings.
    """
    return {
        "run_id": run.run_id,
        "name": run.name,
        "input_text": run.input_text,
        "output_text": run.output_text,
        "result_summary": run.result_summary,
        "start_time": _iso(run.start_time),
        "end_time": _iso(run.end_time),
        "outcome": run.outcome.value,
        "steps": [_step_to_dict(step) for step in run.steps],
        "tool_calls": [_tool_to_dict(call) for call in run.tool_calls],
        "llm_calls": [_llm_to_dict(call) for call in run.llm_calls],
        "retry_count": run.retry_count,
        "fallback_used": run.fallback_used,
        "error_messages": list(run.error_messages),
        "anomalies": list(run.anomalies),
        "cost_usd": run.cost_usd,
    }


def run_from_dict(data: dict) -> AgentRun:
    """Rebuild a run from its wire-format dict.

    Derived fields (outcome, retries, anomalies, cost) are carried for
    completeness but the server re-derives them via analysis, so missing or
    unknown values degrade gracefully.

    Args:
        data: A dict produced by :func:`run_to_dict` (or equivalent JSON).

    Returns:
        The reconstructed run.
    """
    return AgentRun(
        run_id=str(data.get("run_id", "")),
        name=str(data.get("name", "agent")),
        input_text=str(data.get("input_text", "")),
        output_text=str(data.get("output_text", "")),
        result_summary=str(data.get("result_summary", "")),
        start_time=parse_time(data.get("start_time")),
        end_time=parse_time(data.get("end_time")),
        outcome=_parse_outcome(data.get("outcome")),
        steps=[_step_from_dict(item) for item in _dict_items(data.get("steps"))],
        tool_calls=[_tool_from_dict(item) for item in _dict_items(data.get("tool_calls"))],
        llm_calls=[_llm_from_dict(item) for item in _dict_items(data.get("llm_calls"))],
        retry_count=_as_int(data.get("retry_count")),
        fallback_used=bool(data.get("fallback_used", False)),
        error_messages=[str(item) for item in _list_items(data.get("error_messages"))],
        anomalies=[str(item) for item in _list_items(data.get("anomalies"))],
        cost_usd=_as_optional_float(data.get("cost_usd")),
    )


def _step_to_dict(step: Step) -> dict:
    """Serialize one step."""
    return {
        "name": step.name,
        "kind": step.kind,
        "start_time": _iso(step.start_time),
        "end_time": _iso(step.end_time),
        "status": step.status,
        "error": step.error,
        "model_calls": step.model_calls,
        "tool_calls": step.tool_calls,
        "tokens": step.tokens,
    }


def _step_from_dict(data: dict) -> Step:
    """Rebuild one step."""
    return Step(
        name=str(data.get("name", "")),
        kind=str(data.get("kind", "node")),
        start_time=parse_time(data.get("start_time")),
        end_time=parse_time(data.get("end_time")),
        status=str(data.get("status", "success")),
        error=_as_optional_str(data.get("error")),
        model_calls=_as_int(data.get("model_calls")),
        tool_calls=_as_int(data.get("tool_calls")),
        tokens=_as_int(data.get("tokens")),
    )


def _tool_to_dict(call: ToolCall) -> dict:
    """Serialize one tool call."""
    return {
        "name": call.name,
        "arguments": call.arguments,
        "output": call.output,
        "timestamp": _iso(call.timestamp),
        "latency_ms": call.latency_ms,
        "status": call.status,
        "error": call.error,
    }


def _tool_from_dict(data: dict) -> ToolCall:
    """Rebuild one tool call."""
    arguments = data.get("arguments")
    return ToolCall(
        name=str(data.get("name", "")),
        arguments=arguments if isinstance(arguments, dict) else {},
        output=data.get("output"),
        timestamp=parse_time(data.get("timestamp")),
        latency_ms=_as_optional_float(data.get("latency_ms")),
        status=str(data.get("status", "success")),
        error=_as_optional_str(data.get("error")),
    )


def _llm_to_dict(call: LLMCall) -> dict:
    """Serialize one model call."""
    return {
        "name": call.name,
        "model": call.model,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "timestamp": _iso(call.timestamp),
        "latency_ms": call.latency_ms,
        "status": call.status,
        "error": call.error,
    }


def _llm_from_dict(data: dict) -> LLMCall:
    """Rebuild one model call."""
    return LLMCall(
        name=str(data.get("name", "")),
        model=str(data.get("model", "")),
        input_tokens=_as_int(data.get("input_tokens")),
        output_tokens=_as_int(data.get("output_tokens")),
        timestamp=parse_time(data.get("timestamp")),
        latency_ms=_as_optional_float(data.get("latency_ms")),
        status=str(data.get("status", "success")),
        error=_as_optional_str(data.get("error")),
    )


def _parse_outcome(value: object) -> Outcome:
    """Map a wire outcome string to the enum, defaulting to UNKNOWN."""
    try:
        return Outcome(str(value))
    except ValueError:
        return Outcome.UNKNOWN


def _dict_items(value: object) -> list[dict]:
    """Return the dict elements of a wire list, dropping anything malformed."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_items(value: object) -> list:
    """Return a wire value as a list, or empty when absent/malformed."""
    return value if isinstance(value, list) else []


def _as_int(value: object) -> int:
    """Coerce a wire value to a non-negative int, defaulting to 0."""
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


def _as_optional_float(value: object) -> float | None:
    """Coerce a wire value to a float, or None when absent/malformed."""
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _as_optional_str(value: object) -> str | None:
    """Coerce a wire value to a string, preserving None."""
    return None if value is None else str(value)


def _iso(value: datetime | None) -> str | None:
    """Format a datetime as ISO-8601, or None when absent."""
    return value.isoformat() if value is not None else None
