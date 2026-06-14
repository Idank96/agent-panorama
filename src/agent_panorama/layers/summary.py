"""Optional LLM-backed result phrasing.

Rewrites a run's final output into one short, past-tense action sentence (e.g.
"Showed all the open support tickets."). This is the only part of the
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
    "Rewrite the agent's final output as ONE short past-tense sentence with the "
    "bottom-line takeaway. When the agent succeeded, frame it as how it helped "
    "the user reach their goal; if the output is wrong or admits a mistake, say "
    "so plainly instead of spinning it as success. Always keep identifying "
    "details (person, account, project, or ticket names) and the concrete "
    "conclusion, so a manager scanning hundreds of entries can tell them apart. "
    "Plain language, no markdown, no preamble. Example: 'Helped Acme Corp resolve "
    "a billing question — refund issued, ticket closed.'"
)

_SESSION_SYSTEM_PROMPT = (
    "You are given a numbered transcript of one user's multi-turn session with "
    "an agent; each line reads 'asked X → tools → result Y'. Write ONE short "
    "past-tense sentence summarizing what the agent did for the user and the "
    "FINAL bottom-line outcome — use the LAST turn as the outcome. When the "
    "agent succeeded, frame it as how it helped the user; if it gave a wrong "
    "answer or had to correct an earlier one, say so plainly instead of "
    "presenting it as a success. Always keep identifying details (person, "
    "account, project, or ticket names) and the concrete conclusion, so a "
    "manager scanning hundreds of entries can tell them apart. Plain language, "
    "no markdown, no preamble. Examples: 'Helped Acme Corp finish onboarding — "
    "integration is live, handed back to their team.' / 'Corrected an earlier "
    "wrong answer after the user pushed back — confirmed the Moon orbits the "
    "Earth.'"
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


def build_session_exchange(transcript: str, model: str = DEFAULT_MODEL) -> SummaryExchange:
    """Phrase a whole session transcript as one action sentence.

    Mirrors :func:`build_exchange` — capped input, never raises — but uses the
    session prompt, so a multi-turn conversation reads as one "thing" the agent
    did for the user.

    Args:
        transcript: The numbered session transcript (see
            :func:`agent_panorama.analysis.session_transcript`).
        model: A LangChain ``init_chat_model`` identifier.

    Returns:
        A :class:`SummaryExchange` with the exact prompt, input, and output/error.
    """
    snippet = transcript.strip()[:MAX_INPUT_CHARS]
    if not snippet:
        return SummaryExchange(
            model, _SESSION_SYSTEM_PROMPT, "", error="empty transcript; nothing to send"
        )
    try:
        output = _invoke_with(model, snippet, _SESSION_SYSTEM_PROMPT)
        return SummaryExchange(model, _SESSION_SYSTEM_PROMPT, snippet, output=output)
    except Exception as error:  # noqa: BLE001 - never let phrasing break a report
        logger.warning("Session summarization with %s failed: %s", model, error)
        return SummaryExchange(model, _SESSION_SYSTEM_PROMPT, snippet, error=str(error))


def summarize_session(transcript: str, model: str = DEFAULT_MODEL) -> str | None:
    """Phrase a session transcript via a cheap LLM, or None on any failure."""
    return build_session_exchange(transcript, model).output


def _invoke(model: str, snippet: str) -> str:
    """Call the model with the per-run prompt (kept for back-compat in tests)."""
    return _invoke_with(model, snippet, _SYSTEM_PROMPT)


def _invoke_with(model: str, snippet: str, system_prompt: str) -> str:
    """Call the model with the given system prompt and return one clean line."""
    from langchain.chat_models import init_chat_model

    llm = init_chat_model(model)
    response = llm.invoke([("system", system_prompt), ("human", snippet)])
    return _one_line(getattr(response, "content", str(response)))


def _one_line(content: object) -> str:
    """Flatten model output to a single trimmed line."""
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
    return " ".join(str(content).split())
