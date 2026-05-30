"""Trace parsers that normalize vendor exports into :class:`AgentRun` models."""

from __future__ import annotations

from ..models import AgentRun
from . import langfuse, langsmith

# Registry mapping an input-type name to its parse function.
PARSERS = {
    "langfuse": langfuse.parse,
    "langsmith": langsmith.parse,
}


def parse(payload: object, input_type: str = "langfuse") -> list[AgentRun]:
    """Parse a decoded trace export with the named parser.

    Args:
        payload: The decoded JSON export.
        input_type: One of ``"langfuse"`` or ``"langsmith"``.

    Returns:
        A list of normalized :class:`AgentRun` objects.

    Raises:
        ValueError: If ``input_type`` is not a supported parser.
    """
    if input_type not in PARSERS:
        supported = ", ".join(sorted(PARSERS))
        raise ValueError(f"Unsupported input type '{input_type}'. Supported: {supported}.")
    return PARSERS[input_type](payload)


__all__ = ["parse", "PARSERS", "langfuse", "langsmith"]
