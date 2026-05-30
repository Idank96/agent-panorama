"""Shared low-level helpers used by all trace parsers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..models import AgentRun, Step


def fallback_steps(run: AgentRun) -> list[Step]:
    """Synthesize narrative steps when a trace exposes no graph nodes.

    Falls back to one step per tool call, then to a single aggregated model
    step, so every run still reads as a sequence of actions.

    Args:
        run: The run whose tool/model calls should be turned into steps.

    Returns:
        A list of synthesized :class:`Step` objects (possibly empty).
    """
    if run.tool_calls:
        return [
            Step(
                name=call.name,
                kind="tool",
                start_time=call.timestamp,
                status=call.status,
                error=call.error,
                tool_calls=1,
            )
            for call in run.tool_calls
        ]
    if run.llm_calls:
        starts = [c.timestamp for c in run.llm_calls if c.timestamp]
        return [
            Step(
                name="Generated a response",
                kind="model",
                start_time=min(starts) if starts else None,
                status="error" if any(c.status != "success" for c in run.llm_calls) else "success",
                model_calls=len(run.llm_calls),
                tokens=run.total_tokens,
            )
        ]
    return []


def parse_time(value: object) -> datetime | None:
    """Parse a timestamp from a trace into a timezone-aware datetime.

    Accepts ISO 8601 strings (with or without a trailing ``Z``) and epoch
    seconds/milliseconds as numbers.

    Args:
        value: The raw timestamp value.

    Returns:
        A timezone-aware datetime, or None if it cannot be parsed.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _parse_epoch(float(value))
    if isinstance(value, str):
        return _parse_iso(value)
    return None


def _parse_epoch(value: float) -> datetime | None:
    """Parse an epoch value, auto-detecting seconds vs milliseconds."""
    seconds = value / 1000.0 if value > 1e12 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware datetime."""
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def extract_tokens(usage: object) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a usage object.

    Handles the several key conventions used across Langfuse and LangSmith
    exports (``input``/``output``, ``promptTokens``/``completionTokens``,
    ``input_tokens``/``output_tokens``, ``prompt_tokens``/``completion_tokens``).

    Args:
        usage: The raw usage mapping from a generation/run.

    Returns:
        A tuple of ``(input_tokens, output_tokens)``.
    """
    if not isinstance(usage, dict):
        return (0, 0)
    input_keys = ("input", "promptTokens", "prompt_tokens", "input_tokens")
    output_keys = ("output", "completionTokens", "completion_tokens", "output_tokens")
    return (_first_int(usage, input_keys), _first_int(usage, output_keys))


def _first_int(data: dict, keys: tuple[str, ...]) -> int:
    """Return the first key present in ``data`` coerced to a non-negative int."""
    for key in keys:
        if key in data and data[key] is not None:
            try:
                return max(0, int(data[key]))
            except (TypeError, ValueError):
                continue
    return 0


def to_text(value: object, max_length: int = 280) -> str:
    """Render any input/output value as a short single-line string.

    Args:
        value: The value to stringify (str, dict, list, or None).
        max_length: Maximum length before truncating with an ellipsis.

    Returns:
        A cleaned, length-limited single-line string.
    """
    if value is None:
        return ""
    return _truncate(_stringify(value), max_length)


def _truncate(text: str, max_length: int) -> str:
    """Collapse whitespace and truncate a string with an ellipsis."""
    text = " ".join(text.split())
    if len(text) > max_length:
        return text[: max_length - 1].rstrip() + "…"
    return text


_HUMAN_ROLES = frozenset({"human", "user"})
# Roles whose content represents output the agent produced (vs. the user's ask).
_OUTPUT_ROLES = frozenset({"ai", "assistant", "tool", "function"})


def summarize_request(value: object, max_length: int = 280) -> str:
    """Summarize what an agent was asked to do.

    Prefers the first human/user message in a chat-style payload (the original
    ask), falling back to a generic stringification.

    Args:
        value: The trace/run input value.
        max_length: Maximum length of the result.

    Returns:
        A clean, single-line description of the request.
    """
    humans = [content for role, content in _messages(value) if role in _HUMAN_ROLES]
    if humans:
        return _truncate(humans[0], max_length)
    return _truncate(_stringify(_maybe_json(value)), max_length)


def summarize_outcome(value: object, max_length: int = 1000) -> str:
    """Summarize an agent's final result.

    Prefers the last produced message in a chat-style payload (the final
    answer), falling back to a generic stringification. The default cap is
    generous so downstream consumers (the optional LLM summarizer) get real
    context; display truncation is the renderer's job.

    Args:
        value: The trace/run output value.
        max_length: Maximum length of the result.

    Returns:
        A clean, single-line description of the outcome.
    """
    produced = [content for role, content in _messages(value) if role in _OUTPUT_ROLES]
    if produced:
        return _truncate(produced[-1], max_length)
    data = _maybe_json(value)
    if isinstance(data, dict):
        result = _first_content(data, _RESULT_KEYS)
        if result:
            return _truncate(result, max_length)
    return _truncate(_stringify(data), max_length)


def _messages(value: object) -> list[tuple[str, str]]:
    """Extract ``(role, content)`` pairs from a chat-style payload."""
    data = _maybe_json(value)
    raw = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    pairs = [_message_role_content(item) for item in raw]
    return [(role, content) for role, content in pairs if content]


def _message_role_content(message: object) -> tuple[str, str]:
    """Return the ``(role, content)`` of a single message in any common shape."""
    if isinstance(message, (list, tuple)) and len(message) >= 2:
        return (str(message[0]).lower(), _content_text(message[1]))
    if isinstance(message, dict):
        role = str(message.get("type") or message.get("role") or "").lower()
        return (role, _content_text(message.get("content")))
    return ("", "")


def _content_text(content: object) -> str:
    """Flatten message content (string or list of content blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_block_text(block) for block in content]
        return " ".join(part for part in parts if part)
    return "" if content is None else str(content)


def _block_text(block: object) -> str:
    """Extract text from a single content block."""
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        return str(block.get("text") or block.get("content") or "")
    return ""


def _maybe_json(value: object) -> object:
    """Decode a value that is JSON (possibly double-encoded) into Python data.

    Some exporters store the payload as a JSON string, and occasionally as a
    JSON-encoded JSON string (the value starts with ``"``). This unwraps up to a
    few layers until it reaches a container or a plain string.
    """
    result = value
    for _ in range(3):
        if not isinstance(result, str):
            break
        stripped = result.strip()
        if stripped[:1] not in ("{", "[", '"'):
            break
        try:
            result = json.loads(stripped)
        except (ValueError, TypeError):
            break
    return result


def _stringify(value: object) -> str:
    """Convert a value to a string, extracting message content when possible."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _stringify_dict(value)
    if isinstance(value, list):
        parts = [_stringify(item) for item in value]
        return " ".join(part for part in parts if part)
    return str(value)


_CONTENT_KEYS = (
    "content",
    "text",
    "output",
    "input",
    "message",
    "question",
    "task",
    "query",
    "prompt",
    "instruction",
    "description",
)

# Keys that carry an agent's final result in a state/output payload.
_RESULT_KEYS = ("report", "result", "answer", "response", "final_answer", "output")


def _stringify_dict(data: dict) -> str:
    """Pull human-readable content out of common message/payload dicts.

    Falls back to a structural field summary rather than dumping the raw object,
    which keeps large state payloads readable and avoids leaking embedded
    secrets (e.g. API tokens) into the report.
    """
    content = _first_content(data, _CONTENT_KEYS)
    return content or _structural_summary(data)


def _first_content(data: dict, keys: tuple[str, ...]) -> str:
    """Return the stringified value of the first present, truthy key."""
    for key in keys:
        if key in data and data[key]:
            return _stringify(data[key])
    return ""


def _structural_summary(data: dict, max_fields: int = 6) -> str:
    """Summarize an unrecognized dict by its field names, never its values."""
    keys = [str(key) for key in data]
    if not keys:
        return ""
    shown = ", ".join(keys[:max_fields])
    suffix = f", … ({len(keys)} fields)" if len(keys) > max_fields else ""
    return f"state with fields: {shown}{suffix}"
