"""Parser for LangSmith run exports.

LangSmith represents work as a tree of *runs*, each with a ``run_type``
(``chain``, ``llm``, ``tool``). A root run (no ``parent_run_id``) corresponds to
one agent execution; this parser flattens each tree into an
:class:`~agent_panorama.models.AgentRun`.
"""

from __future__ import annotations

from ..models import AgentRun, LLMCall, Step, ToolCall
from .common import (
    extract_tokens,
    fallback_steps,
    parse_time,
    summarize_outcome,
    summarize_request,
    to_text,
)

# Framework plumbing runs that wrap real steps; unwrapped, never shown as a step.
_NOISE_RUN_NAMES = frozenset(
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
    }
)


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
    session_id, user_id = _identity(root)
    run = AgentRun(
        run_id=str(root.get("id", "")),
        name=str(root.get("name") or "agent"),
        session_id=session_id,
        user_id=user_id,
        input_text=summarize_request(root.get("inputs")),
        output_text=summarize_outcome(root.get("outputs")),
        start_time=parse_time(root.get("start_time")),
        end_time=parse_time(root.get("end_time")),
    )
    for node in nodes:
        _ingest_run(node, run)
    run.steps = _build_steps(root, by_parent, run)
    return run


def _identity(root: dict) -> tuple[str | None, str | None]:
    """Extract the conversation session and user ids from a root run.

    Deliberately ignores the top-level ``session_id`` — in LangSmith exports it
    is the tracer project id, not a user conversation. Conversation identity
    lives in ``extra.metadata`` (``thread_id``/``session_id``/``user_id``).
    """
    extra = root.get("extra")
    extra = extra if isinstance(extra, dict) else {}
    metadata = extra.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    session = metadata.get("session_id") or metadata.get("thread_id")
    user = metadata.get("user_id") or metadata.get("actor")
    return (str(session) if session else None, str(user) if user else None)


def _build_steps(root: dict, by_parent: dict[str, list[dict]], run: AgentRun) -> list[Step]:
    """Derive the run's ordered narrative from the LangSmith run tree.

    Steps are the top-most meaningful child runs (tools or named graph nodes),
    unwrapping framework plumbing. Falls back to the run's tool calls, then to a
    single aggregated model step, when no such runs exist.
    """
    step_runs: list[dict] = []
    _collect_step_runs(by_parent.get(str(root.get("id")), []), by_parent, step_runs)
    steps = [_run_to_step(node, by_parent) for node in step_runs]
    steps.sort(key=lambda s: s.start_time.timestamp() if s.start_time else float("inf"))
    return steps or fallback_steps(run)


def _collect_step_runs(
    nodes: list[dict], by_parent: dict[str, list[dict]], out: list[dict]
) -> None:
    """Collect the top-most meaningful runs, unwrapping plumbing in between."""
    for node in nodes:
        if _is_step_run(node):
            out.append(node)
        elif (node.get("run_type") or "").lower() != "llm":
            _collect_step_runs(by_parent.get(str(node.get("id")), []), by_parent, out)


def _is_step_run(node: dict) -> bool:
    """Whether a run stands on its own as an agent step."""
    if (node.get("run_type") or "").lower() not in ("tool", "chain", "agent", "retriever"):
        return False
    return (node.get("name") or "").strip().lower() not in _NOISE_RUN_NAMES


def _run_to_step(node: dict, by_parent: dict[str, list[dict]]) -> Step:
    """Build a :class:`Step` from a run, aggregating its subtree activity."""
    subtree = _descendants(node, by_parent)
    model_calls = sum(1 for n in subtree if (n.get("run_type") or "").lower() == "llm")
    tool_calls = sum(1 for n in subtree if (n.get("run_type") or "").lower() == "tool")
    tokens = sum(sum(_llm_tokens(n)) for n in subtree if (n.get("run_type") or "").lower() == "llm")
    errored = next((n for n in subtree if n.get("error")), None)
    return Step(
        name=str(node.get("name") or "step"),
        kind="tool" if (node.get("run_type") or "").lower() == "tool" else "node",
        start_time=parse_time(node.get("start_time")),
        end_time=parse_time(node.get("end_time")),
        status="error" if errored else "success",
        error=to_text(errored.get("error")) if errored else None,
        model_calls=model_calls,
        tool_calls=tool_calls,
        tokens=tokens,
    )


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
