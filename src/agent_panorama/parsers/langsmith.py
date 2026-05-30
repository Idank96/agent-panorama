"""Parser for LangSmith run exports.

LangSmith represents work as a tree of *runs*, each with a ``run_type``
(``chain``, ``llm``, ``tool``). A root run (no ``parent_run_id``) corresponds to
one agent execution; this parser flattens each tree into an
:class:`~agent_panorama.models.AgentRun`.
"""

from __future__ import annotations

from ..models import AgentRun, LLMCall, ToolCall
from .common import extract_tokens, parse_time, summarize_outcome, summarize_request, to_text


def parse(payload: object) -> list[AgentRun]:
    """Parse a LangSmith export into a list of agent runs.

    Args:
        payload: The decoded JSON. May be a single run, a list of runs, or a
            ``{"runs": [...]}`` / ``{"data": [...]}`` wrapper.

    Returns:
        One :class:`AgentRun` per root run in the export.
    """
    runs = _extract_runs(payload)
    by_parent = _group_by_parent(runs)
    roots = [r for r in runs if not r.get("parent_run_id")]
    if not roots:
        roots = runs
    return [_parse_root(root, by_parent) for root in roots]


def _extract_runs(payload: object) -> list[dict]:
    """Normalize the various LangSmith export shapes into a flat list of runs."""
    if isinstance(payload, dict):
        for key in ("runs", "data"):
            if isinstance(payload.get(key), list):
                return [r for r in payload[key] if isinstance(r, dict)]
        return [payload]
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def _group_by_parent(runs: list[dict]) -> dict[str, list[dict]]:
    """Index child runs by their ``parent_run_id``."""
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        parent = run.get("parent_run_id")
        if parent:
            grouped.setdefault(str(parent), []).append(run)
    return grouped


def _descendants(root: dict, by_parent: dict[str, list[dict]]) -> list[dict]:
    """Return the root run and all of its descendants, depth-first."""
    result = [root]
    for child in by_parent.get(str(root.get("id")), []):
        result.extend(_descendants(child, by_parent))
    return result


def _parse_root(root: dict, by_parent: dict[str, list[dict]]) -> AgentRun:
    """Build an :class:`AgentRun` from a root run and its descendants."""
    nodes = _descendants(root, by_parent)
    run = AgentRun(
        run_id=str(root.get("id", "")),
        name=str(root.get("name") or "agent"),
        input_text=summarize_request(root.get("inputs")),
        output_text=summarize_outcome(root.get("outputs")),
        start_time=parse_time(root.get("start_time")),
        end_time=parse_time(root.get("end_time")),
    )
    for node in nodes:
        _ingest_run(node, run)
    return run


def _ingest_run(node: dict, run: AgentRun) -> None:
    """Route a single LangSmith run node into the agent run."""
    run_type = (node.get("run_type") or "").lower()
    if run_type == "llm":
        run.llm_calls.append(_to_llm_call(node))
    elif run_type == "tool":
        run.tool_calls.append(_to_tool_call(node))
    if node.get("error"):
        run.error_messages.append(to_text(node.get("error")))


def _to_llm_call(node: dict) -> LLMCall:
    """Build an :class:`LLMCall` from an ``llm`` run node."""
    input_tokens, output_tokens = _llm_tokens(node)
    return LLMCall(
        name=str(node.get("name") or "llm"),
        model=_model_name(node),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        timestamp=parse_time(node.get("start_time")),
        latency_ms=_latency_ms(node),
        status="error" if node.get("error") else "success",
        error=to_text(node.get("error")) or None,
    )


def _llm_tokens(node: dict) -> tuple[int, int]:
    """Extract token usage from a LangSmith ``llm`` run."""
    usage = node.get("usage_metadata")
    if isinstance(usage, dict):
        return extract_tokens(usage)
    outputs = node.get("outputs")
    if isinstance(outputs, dict):
        nested = outputs.get("llm_output") or outputs.get("usage")
        if isinstance(nested, dict):
            return extract_tokens(nested.get("token_usage") or nested)
    return (0, 0)


def _model_name(node: dict) -> str:
    """Resolve the model name from a run's extra/metadata fields."""
    extra = node.get("extra")
    extra = extra if isinstance(extra, dict) else {}
    metadata = extra.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    invocation = extra.get("invocation_params")
    invocation = invocation if isinstance(invocation, dict) else {}
    return str(
        metadata.get("ls_model_name")
        or invocation.get("model")
        or invocation.get("model_name")
        or node.get("name")
        or ""
    )


def _to_tool_call(node: dict) -> ToolCall:
    """Build a :class:`ToolCall` from a ``tool`` run node."""
    return ToolCall(
        name=str(node.get("name") or "tool"),
        arguments=_coerce_inputs(node.get("inputs")),
        output=node.get("outputs"),
        timestamp=parse_time(node.get("start_time")),
        latency_ms=_latency_ms(node),
        status="error" if node.get("error") else "success",
        error=to_text(node.get("error")) or None,
    )


def _coerce_inputs(value: object) -> dict:
    """Coerce a tool run's ``inputs`` into a dict for rendering."""
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {"value": value}


def _latency_ms(node: dict) -> float | None:
    """Compute a run node's latency in milliseconds from start/end times."""
    start = parse_time(node.get("start_time"))
    end = parse_time(node.get("end_time"))
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() * 1000.0)
