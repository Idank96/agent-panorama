"""The value judge: LLM-as-a-judge over a conversation's turns.

Mirrors the summarization layer's contract: strictly opt-in, lazy langchain
import, capped input, and never raises — any failure is recorded on the
returned exchange so a missing provider or key can never break a report.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

from ...models import AgentRun, ValueJudgment
from .context import ValueContext
from .prompts import JUDGE_SYSTEM_PROMPT, Exchange, build_judge_messages

logger = logging.getLogger(__name__)

# Judging needs more reasoning than one-line phrasing, so the default steps up
# from flash-lite to flash; still cheap, overridable via config.
DEFAULT_JUDGE_MODEL = "google_genai:gemini-2.5-flash"

# Caps keep a judgment call bounded: each side of an exchange is truncated,
# and the whole user message (context + transcript) is hard-capped.
MAX_EXCHANGE_CHARS = 2000
MAX_TRANSCRIPT_CHARS = 8000


@dataclass
class ValueJudgmentExchange:
    """A full record of one judge call, for logging/auditing.

    Shaped like :class:`~agent_panorama.layers.summary.SummaryExchange` so the
    same ``llm_calls.log`` machinery renders it.
    """

    model: str
    system_prompt: str
    input_text: str
    judgment: ValueJudgment | None = None
    error: str | None = None

    @property
    def output(self) -> str | None:
        """The judgment as one JSON line, or None when the call failed."""
        if self.judgment is None:
            return None
        return json.dumps(asdict(self.judgment), ensure_ascii=False)


def judge_session(
    turns: list[AgentRun],
    context: ValueContext | None = None,
    model: str = DEFAULT_JUDGE_MODEL,
    chat_model: object | None = None,
) -> ValueJudgmentExchange:
    """Judge the value one conversation delivered, capturing the full exchange.

    Never raises: provider/key failures are recorded in ``error`` and leave
    ``judgment`` as None, so a missing model can never break a report.

    Args:
        turns: The conversation's runs, ordered by start time.
        context: The customer's value definition for this agent, or None for
            the generic rubric.
        model: A LangChain ``init_chat_model`` identifier.
        chat_model: Optional pre-built chat model (used by tests); when given,
            ``model`` is informational only.

    Returns:
        A :class:`ValueJudgmentExchange` with the exact prompts sent and the
        judgment (or error).
    """
    exchanges = exchanges_from_turns(turns)
    if not exchanges:
        return ValueJudgmentExchange(
            model, JUDGE_SYSTEM_PROMPT, "", error="no usable exchanges in conversation"
        )
    messages = build_judge_messages(exchanges, context)
    messages[1] = {"role": "user", "content": _cap(messages[1]["content"])}
    try:
        judgment = _invoke_judge(model, messages, chat_model)
        return ValueJudgmentExchange(
            model, messages[0]["content"], messages[1]["content"], judgment=judgment
        )
    except Exception as error:  # noqa: BLE001 - never let judging break a report
        logger.warning("Value judging with %s failed: %s", model, error)
        return ValueJudgmentExchange(
            model, messages[0]["content"], messages[1]["content"], error=str(error)
        )


def exchanges_from_turns(turns: list[AgentRun]) -> list[Exchange]:
    """Map a conversation's runs to judge exchanges, dropping empty turns.

    Args:
        turns: The conversation's runs, ordered by start time.

    Returns:
        One :class:`Exchange` per turn that has any input or output text,
        each side truncated to :data:`MAX_EXCHANGE_CHARS`.
    """
    exchanges = []
    for run in turns:
        user = run.input_text.strip()[:MAX_EXCHANGE_CHARS]
        assistant = run.output_text.strip()[:MAX_EXCHANGE_CHARS]
        if user or assistant:
            exchanges.append(Exchange(user_input=user, assistant_output=assistant))
    return exchanges


def _cap(content: str) -> str:
    """Hard-cap the judge's user message, marking any truncation."""
    if len(content) <= MAX_TRANSCRIPT_CHARS:
        return content
    return content[:MAX_TRANSCRIPT_CHARS] + "\n[transcript truncated]"


def _invoke_judge(
    model: str, messages: list[dict[str, str]], chat_model: object | None
) -> ValueJudgment:
    """Call the judge model with structured output and return a plain judgment."""
    from ._schema import ValueReportSchema

    if chat_model is None:
        from langchain.chat_models import init_chat_model

        chat_model = init_chat_model(model, temperature=0)
    structured = chat_model.with_structured_output(ValueReportSchema)  # type: ignore[attr-defined]
    result = structured.invoke(messages)
    data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    return ValueJudgment(**data)
