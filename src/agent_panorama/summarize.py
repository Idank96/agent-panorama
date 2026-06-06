"""Back-compat shim: the summarization layer lives in :mod:`.layers.summary`."""

from .layers.summary import (
    DEFAULT_MODEL,
    MAX_INPUT_CHARS,
    SummaryExchange,
    build_exchange,
    build_session_exchange,
    summarize_result,
    summarize_session,
)

__all__ = [
    "DEFAULT_MODEL",
    "MAX_INPUT_CHARS",
    "SummaryExchange",
    "build_exchange",
    "build_session_exchange",
    "summarize_result",
    "summarize_session",
]
