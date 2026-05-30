"""Optional LLM-backed result phrasing.

Rewrites a run's final output into one short, past-tense action sentence (e.g.
"Showed all the cutting stations in the plant."). This is the only part of the
package that may call an external model, and it is strictly opt-in: nothing here
runs unless the caller passes ``summarize=True``.

It is deliberately minimal to keep cost negligible: a tiny fixed system prompt
and a hard cap on the input it sends. See :data:`MAX_INPUT_CHARS`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# The cheapest sensible default: Gemini Flash-Lite has a genuine no-credit-card
# free tier, so this workload is free to run. Overridable via config/CLI.
DEFAULT_MODEL = "google_genai:gemini-2.5-flash-lite"

# Hard cap on the characters of the result we send (~1 token per 4 chars), so a
# summarization call costs roughly _MAX_INPUT_CHARS/4 input tokens plus the
# system prompt (~40 tokens) and a one-line completion (~25 tokens).
MAX_INPUT_CHARS = 1000

_SYSTEM_PROMPT = (
    "Rewrite the agent's final output as ONE short past-tense sentence stating "
    "what the agent did for the user. Plain language, no markdown, no data, no "
    "preamble. Example: 'Showed all the cutting stations in the plant.'"
)


@dataclass
class SummaryExchange:
    """A full record of one summarization call, for logging/auditing."""

    model: str
    system_prompt: str
    input_text: str
    output: str | None = None
    error: str | None = None


def build_exchange(text: str, model: str = DEFAULT_MODEL) -> SummaryExchange:
    """Run one summarization call and capture the full exchange.

    Never raises: provider/key failures are recorded in ``error`` and leave
    ``output`` as None, so a missing model can never break report generation.

    Args:
        text: The run's final output text.
        model: A LangChain ``init_chat_model`` identifier, e.g.
            ``"google_genai:gemini-2.5-flash-lite"`` or ``"openai:gpt-5-nano"``.

    Returns:
        A :class:`SummaryExchange` with the exact system prompt, input sent, and
        output (or error).
    """
    snippet = text.strip()[:MAX_INPUT_CHARS]
    if not snippet:
        return SummaryExchange(model, _SYSTEM_PROMPT, "", error="empty result; nothing to send")
    try:
        return SummaryExchange(model, _SYSTEM_PROMPT, snippet, output=_invoke(model, snippet))
    except Exception as error:  # noqa: BLE001 - never let phrasing break a report
        logger.warning("Result summarization with %s failed: %s", model, error)
        return SummaryExchange(model, _SYSTEM_PROMPT, snippet, error=str(error))


def summarize_result(text: str, model: str = DEFAULT_MODEL) -> str | None:
    """Rewrite a result into one short action sentence via a cheap LLM.

    Thin wrapper over :func:`build_exchange` returning just the summary text, or
    None if summarization is unavailable or fails.
    """
    return build_exchange(text, model).output


def _invoke(model: str, snippet: str) -> str:
    """Call the model and return a cleaned one-line summary."""
    from langchain.chat_models import init_chat_model

    llm = init_chat_model(model)
    response = llm.invoke([("system", _SYSTEM_PROMPT), ("human", snippet)])
    return _one_line(getattr(response, "content", str(response)))


def _one_line(content: object) -> str:
    """Flatten model output to a single trimmed line."""
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
    return " ".join(str(content).split())
