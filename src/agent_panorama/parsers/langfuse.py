"""Parser for Langfuse trace exports.

A Langfuse trace is an object with an ``observations`` list. Observations are
typed ``GENERATION`` (model calls), ``TOOL`` (tool executions), ``SPAN`` (units
of work), ``EVENT``, ``AGENT``, or ``CHAIN`` (orchestration). This parser
normalizes each trace into an :class:`~agent_panorama.models.AgentRun`.

Supported export shapes:
    * a single trace dict with nested ``observations``;
    * the single-trace API shape ``{"trace": {...}, "observations": [...]}``;
    * a list of any of the above;
    * the list API shape ``{"data": [...]}``.
"""

from __future__ import annotations

from datetime import datetime

from ..models import AgentRun, LLMCall, Step, ToolCall
from .common import (
    extract_tokens,
    fallback_steps,
    parse_time,
    summarize_outcome,
    summarize_request,
    to_text,
)

# Span/event names that wrap orchestration rather than a real tool call.
_NON_TOOL_HINTS = ("agent", "chain", "graph", "runnable", "llm", "retriever", "embedding")

# Framework plumbing nodes that wrap real steps; unwrapped, never shown as a step.
_NOISE_NODE_NAMES = frozenset(
    {
        "chatprompttemplate",
        "runnablesequence",
        "runnablelambda",
        "runnableparallel",
        "runnableassign",
        "runnablemap",
        "runnablewithfallbacks",
        "runnablecallable",
        "langgraph",
        "__start__",
        "__end__",
        "channel_write",
        "model",
        "tools",
        "tool",
        "agent",
        "should_continue",
    }
)

# Observation types that can stand on their own as an agent step.
_STEP_TYPES = frozenset({"CHAIN", "AGENT", "SPAN", "TOOL"})


def parse(payload: object) -> list[AgentRun]:
    """Parse a Langfuse export into a list of agent runs.

    Args:
        payload: The decoded JSON in any of the supported export shapes.

    Returns:
        One :class:`AgentRun` per trace.
    """
    traces = _extract_traces(payload)
    return [_parse_trace(trace) for trace in traces]


def _extract_traces(payload: object) -> list[dict]:
    """Normalize the various Langfuse export shapes into a list of traces.

    Each returned dict is a trace with its observations attached under the
    ``observations`` key.
    """
    if isinstance(payload, list):
        return [_normalize_trace(t) for t in payload if isinstance(t, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return [_normalize_trace(t) for t in payload["data"] if isinstance(t, dict)]
        return [_normalize_trace(payload)]
    return []


def _normalize_trace(item: dict) -> dict:
    """Return a trace dict with observations attached under ``observations``.

    Handles the ``{"trace": {...}, "observations": [...]}`` shape where the
    observations are a sibling of the trace rather than nested inside it.
    """
    if isinstance(item.get("trace"), dict):
        trace = dict(item["trace"])
        siblings = item.get("observations")
        if isinstance(siblings, list) and siblings:
            trace["observations"] = siblings
        return trace
    return item


def _parse_trace(trace: dict) -> AgentRun:
    """Convert a single Langfuse trace dict into an :class:`AgentRun`."""
    observations = _sorted_observations(trace.get("observations") or [])
    run = AgentRun(
        run_id=str(trace.get("id", "")),
        name=str(trace.get("name") or "agent"),
        input_text=summarize_request(trace.get("input")),
        output_text=summarize_outcome(trace.get("output")),
        start_time=parse_time(trace.get("timestamp") or trace.get("createdAt")),
    )
    executed_calls: list[ToolCall] = []
    gen_calls: list[ToolCall] = []
    has_tool_type = any((o.get("type") or "").upper() == "TOOL" for o in observations)
    for obs in observations:
        _ingest_observation(obs, run, executed_calls, gen_calls, has_tool_type)
    run.tool_calls = _merge_tool_calls(executed_calls, gen_calls)
    run.steps = _build_steps(observations, run)
    _backfill_times(run, observations)
    return run


def _merge_tool_calls(executed_calls: list[ToolCall], gen_calls: list[ToolCall]) -> list[ToolCall]:
    """Combine executed and model-declared tool calls.

    When a generation declares a tool that is also executed (as a ``TOOL`` or
    tool ``SPAN`` observation), the execution is authoritative, so the
    declaration is dropped to avoid double-counting.
    """
    executed_names = {call.name for call in executed_calls}
    merged = executed_calls + [call for call in gen_calls if call.name not in executed_names]
    merged.sort(key=lambda c: c.timestamp.timestamp() if c.timestamp else float("inf"))
    return merged


def _sorted_observations(observations: list) -> list[dict]:
    """Return observation dicts sorted by start time (stable for missing times)."""
    obs = [o for o in observations if isinstance(o, dict)]
    return sorted(obs, key=lambda o: parse_time(o.get("startTime")) or datetime.min)


def _build_steps(observations: list[dict], run: AgentRun) -> list[Step]:
    """Derive the run's ordered narrative from the observation tree.

    The steps are the top-most *meaningful* nodes (graph nodes or tools),
    unwrapping framework plumbing (the LangGraph root, ChatPromptTemplate,
    Runnable wrappers). When a trace exposes no such nodes, falls back to the
    run's tool calls, then to a single aggregated model step.
    """
    children = _children_by_parent(observations)
    by_id = {o.get("id") for o in observations if o.get("id")}
    roots = [o for o in observations if o.get("parentObservationId") not in by_id]
    candidates = children.get(roots[0].get("id"), []) or roots if len(roots) == 1 else roots
    step_nodes: list[dict] = []
    _collect_step_nodes(candidates, children, step_nodes)
    steps = [_node_to_step(node, children) for node in step_nodes]
    steps.sort(key=lambda s: s.start_time.timestamp() if s.start_time else float("inf"))
    return steps or fallback_steps(run)


def _children_by_parent(observations: list[dict]) -> dict[object, list[dict]]:
    """Index observations by their ``parentObservationId``."""
    children: dict[object, list[dict]] = {}
    for obs in observations:
        children.setdefault(obs.get("parentObservationId"), []).append(obs)
    return children


def _collect_step_nodes(
    nodes: list[dict], children: dict[object, list[dict]], out: list[dict]
) -> None:
    """Collect the top-most meaningful nodes, unwrapping plumbing in between."""
    for node in nodes:
        if _is_step_node(node):
            out.append(node)
        else:
            _collect_step_nodes(children.get(node.get("id"), []), children, out)


def _is_step_node(obs: dict) -> bool:
    """Whether an observation stands on its own as an agent step.

    Tool executions are always steps; orchestration nodes (chains/agents/spans)
    count only when their name is not framework plumbing (a graph wrapper like
    ``model``/``tools`` or a middleware hook like ``*.before_model``).
    """
    obs_type = (obs.get("type") or "").upper()
    if obs_type == "TOOL":
        return True
    if obs_type not in _STEP_TYPES:
        return False
    return not _is_noise_name(obs.get("name"))


def _is_noise_name(name: object) -> bool:
    """Whether a node name is framework plumbing rather than a real step."""
    text = str(name or "").strip().lower()
    if not text or text in _NOISE_NODE_NAMES:
        return True
    return ".before_" in text or ".after_" in text or "middleware" in text


def _node_to_step(node: dict, children: dict[object, list[dict]]) -> Step:
    """Build a :class:`Step` from a node, aggregating its subtree activity."""
    subtree = _subtree(node, children)
    model_calls = sum(1 for o in subtree if (o.get("type") or "").upper() == "GENERATION")
    tool_calls = sum(1 for o in subtree if (o.get("type") or "").upper() == "TOOL")
    tokens = sum(sum(_generation_tokens(o)) for o in subtree)
    errored = next((o for o in subtree if (o.get("level") or "").upper() == "ERROR"), None)
    is_tool = (node.get("type") or "").upper() == "TOOL" or _is_tool_span(node)
    return Step(
        name=str(node.get("name") or "step"),
        kind="tool" if is_tool else "node",
        start_time=parse_time(node.get("startTime")),
        end_time=parse_time(node.get("endTime")),
        status="error" if errored else "success",
        error=to_text(errored.get("statusMessage") or errored.get("output")) if errored else None,
        model_calls=model_calls,
        tool_calls=tool_calls,
        tokens=tokens,
    )


def _subtree(node: dict, children: dict[object, list[dict]]) -> list[dict]:
    """Return a node and all of its descendants, depth-first."""
    result = [node]
    for child in children.get(node.get("id"), []):
        result.extend(_subtree(child, children))
    return result


def _ingest_observation(
    obs: dict,
    run: AgentRun,
    executed_calls: list[ToolCall],
    gen_calls: list[ToolCall],
    has_tool_type: bool,
) -> None:
    """Route one observation into the run's model calls and tool-call buckets.

    ``TOOL`` observations are authoritative tool executions. ``SPAN``/``EVENT``
    observations are only treated as tools when the trace has no ``TOOL``-typed
    observations, so nested spans under a tool are not double-counted.
    """
    obs_type = (obs.get("type") or "").upper()
    if obs_type == "GENERATION":
        run.llm_calls.append(_to_llm_call(obs))
        gen_calls.extend(_tool_calls_from_generation(obs))
    elif obs_type == "TOOL" or (not has_tool_type and _is_tool_span(obs)):
        executed_calls.append(_to_tool_call(obs))
    if (obs.get("level") or "").upper() == "ERROR":
        message = to_text(obs.get("statusMessage") or obs.get("output"))
        if message:
            run.error_messages.append(message)


def _to_llm_call(obs: dict) -> LLMCall:
    """Build an :class:`LLMCall` from a GENERATION observation."""
    input_tokens, output_tokens = _generation_tokens(obs)
    return LLMCall(
        name=str(obs.get("name") or "generation"),
        model=str(obs.get("model") or ""),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        timestamp=parse_time(obs.get("startTime")),
        latency_ms=_latency_ms(obs),
        status=_status(obs),
        error=_error_message(obs),
    )


def _generation_tokens(obs: dict) -> tuple[int, int]:
    """Extract prompt/completion tokens from a GENERATION observation.

    Prefers Langfuse's flat ``inputUsage``/``outputUsage`` fields, falling back
    to the nested ``usage``/``usageDetails`` mappings used by other exports.
    """
    if obs.get("inputUsage") is not None or obs.get("outputUsage") is not None:
        return (int(obs.get("inputUsage") or 0), int(obs.get("outputUsage") or 0))
    return extract_tokens(obs.get("usage") or obs.get("usageDetails"))


def _tool_calls_from_generation(obs: dict) -> list[ToolCall]:
    """Extract tool calls declared by a generation.

    Reads the dedicated Langfuse ``toolCalls`` field, then falls back to
    OpenAI-style ``tool_calls`` embedded in the generation output and, last,
    to the bare ``toolCallNames`` list.
    """
    timestamp = parse_time(obs.get("startTime"))
    declared = obs.get("toolCalls")
    raw_calls = declared if _is_spec_list(declared) else _find_tool_calls(obs.get("output"))
    if raw_calls:
        return [_tool_call_from_spec(spec, timestamp) for spec in raw_calls]
    names = obs.get("toolCallNames")
    if isinstance(names, list):
        return [ToolCall(name=str(n), arguments={}, timestamp=timestamp) for n in names if n]
    return []


def _is_spec_list(value: object) -> bool:
    """Whether a value is a non-empty list of tool-call spec dicts."""
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _find_tool_calls(output: object) -> list[dict]:
    """Locate a ``tool_calls`` list inside common message output shapes."""
    if isinstance(output, dict):
        if isinstance(output.get("tool_calls"), list):
            return [c for c in output["tool_calls"] if isinstance(c, dict)]
        for value in output.values():
            found = _find_tool_calls(value)
            if found:
                return found
    if isinstance(output, list):
        for item in output:
            found = _find_tool_calls(item)
            if found:
                return found
    return []


def _tool_call_from_spec(spec: dict, timestamp: datetime | None) -> ToolCall:
    """Build a :class:`ToolCall` from an OpenAI-style tool_call spec."""
    raw_function = spec.get("function")
    function = raw_function if isinstance(raw_function, dict) else spec
    name = str(function.get("name") or spec.get("name") or "tool")
    arguments = function.get("arguments", spec.get("args", {}))
    return ToolCall(name=name, arguments=_coerce_args(arguments), timestamp=timestamp)


def _is_tool_span(obs: dict) -> bool:
    """Decide whether a SPAN/EVENT observation represents a tool execution."""
    obs_type = (obs.get("type") or "").upper()
    if obs_type not in ("SPAN", "EVENT"):
        return False
    metadata = _metadata(obs)
    if metadata.get("tool") or metadata.get("tool_name"):
        return True
    name = (obs.get("name") or "").lower()
    if not name:
        return False
    return not any(hint in name for hint in _NON_TOOL_HINTS)


def _metadata(obs: dict) -> dict:
    """Return an observation's metadata mapping, or an empty dict."""
    metadata = obs.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _to_tool_call(obs: dict) -> ToolCall:
    """Build a :class:`ToolCall` from a tool SPAN/EVENT observation."""
    metadata = _metadata(obs)
    name = str(metadata.get("tool_name") or metadata.get("tool") or obs.get("name") or "tool")
    return ToolCall(
        name=name,
        arguments=_coerce_args(obs.get("input")),
        output=obs.get("output"),
        timestamp=parse_time(obs.get("startTime")),
        latency_ms=_latency_ms(obs),
        status=_status(obs),
        error=_error_message(obs),
    )


def _coerce_args(value: object) -> dict:
    """Coerce tool arguments into a dict for uniform downstream rendering."""
    import json

    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except (ValueError, TypeError):
            return {"value": value}
    if value is None:
        return {}
    return {"value": value}


def _latency_ms(obs: dict) -> float | None:
    """Compute observation latency in milliseconds from start/end times."""
    start = parse_time(obs.get("startTime"))
    end = parse_time(obs.get("endTime"))
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() * 1000.0)


def _status(obs: dict) -> str:
    """Map a Langfuse observation level to a success/error status."""
    return "error" if (obs.get("level") or "").upper() == "ERROR" else "success"


def _error_message(obs: dict) -> str | None:
    """Return the status message when an observation errored."""
    if (obs.get("level") or "").upper() != "ERROR":
        return None
    return to_text(obs.get("statusMessage")) or None


def _backfill_times(run: AgentRun, observations: list[dict]) -> None:
    """Fill in run start/end from observation times when trace times are absent."""
    starts = [t for t in (parse_time(o.get("startTime")) for o in observations) if t]
    ends = [t for t in (parse_time(o.get("endTime")) for o in observations) if t]
    if run.start_time is None and starts:
        run.start_time = min(starts)
    if run.end_time is None and ends:
        run.end_time = max(ends)
