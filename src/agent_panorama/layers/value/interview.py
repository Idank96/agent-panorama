"""The guided value-definition interview: an adaptive, one-question-at-a-time
discovery flow that helps a non-technical manager define how their agent's value
is measured — in their own domain language.

Stateless by design: the caller (the live server, on behalf of the dashboard
wizard) holds the transcript and the partial :class:`ValueContext`, and each
step is one cheap LLM call that returns the single most useful next question (or
``done``). Mirrors the rest of the value layer: lazy pydantic in ``_schema.py``,
the same ``init_chat_model`` provider path, and it **never raises** — any error
or missing provider degrades to a deterministic fixed-order fallback so the
wizard always advances.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .context import ValueContext

logger = logging.getLogger(__name__)

# Same cheap tier as the mapping layer; the server passes its summarize model.
DEFAULT_INTERVIEW_MODEL = "google_genai:gemini-2.5-flash-lite"

# The definition is complete enough to stop once these are captured; the cap
# keeps the interview short even if the model never volunteers ``done``.
MAX_QUESTIONS = 8
MIN_SUCCESS_CRITERIA = 2

_FIELDS = ("domain", "user_goal", "success_criteria", "custom_dimensions")
_INPUT_KIND = {
    "domain": "text",
    "user_goal": "longtext",
    "success_criteria": "list",
    "custom_dimensions": "dimensions",
}

_FALLBACK = {
    "domain": (
        "What does this agent help your users do, and in what setting?",
        "Sets the language value is judged in — your domain, not a generic rubric.",
        ["B2B SaaS billing support", "Internal IT helpdesk", "E-commerce order support"],
    ),
    "user_goal": (
        "What is a user trying to achieve in a conversation with this agent?",
        "Value is judged against this goal, not a checklist.",
        ["Resolve the issue without a human", "Get an accurate answer fast"],
    ),
    "success_criteria": (
        "What marks a genuinely good outcome? Add a few concrete checks.",
        "Each is reported met / not met for every conversation.",
        ["Issue resolved without escalation", "No repeat contact within 48h"],
    ),
    "custom_dimensions": (
        "What qualities should every conversation be scored on, 0-10?",
        "Named qualities that matter to you beyond a simple pass/fail.",
        ["empathy", "first-contact resolution", "proactiveness"],
    ),
}


@dataclass
class InterviewTurn:
    """One answered question, as the model sees the history."""

    field_name: str
    prompt: str
    answer: str


@dataclass
class InterviewStep:
    """The next thing the wizard should render (or ``done``)."""

    done: bool
    field_name: str | None = None
    prompt: str = ""
    help: str = ""
    input_kind: str = "text"
    suggestions: list[str] = field(default_factory=list)
    recap: str = ""


def advance_interview(
    agent_name: str,
    transcript: list[InterviewTurn],
    current: ValueContext,
    model: str = DEFAULT_INTERVIEW_MODEL,
    chat_model: object | None = None,
) -> InterviewStep:
    """Return the next interview step given the conversation so far.

    Never raises: a missing provider/key or any model error degrades to the
    deterministic fixed-order fallback, so the wizard always advances.

    Args:
        agent_name: Display name of the agent being defined (for phrasing).
        transcript: The answered questions so far.
        current: The value definition assembled so far.
        model: A LangChain ``init_chat_model`` identifier.
        chat_model: Optional pre-built chat model (tests); ``model`` is then
            informational only.

    Returns:
        The next :class:`InterviewStep`.
    """
    if len(transcript) >= MAX_QUESTIONS:
        return _done_step(current)
    try:
        step = _invoke_advance(agent_name, transcript, current, model, chat_model)
    except Exception as error:  # noqa: BLE001 - the wizard must always advance
        logger.warning("Value interview advance failed: %s", error)
        return _fallback_step(current)
    if step.done and not _meets_minimums(current):
        return _fallback_step(current)
    return step


def suggest_options(
    agent_name: str,
    current: ValueContext,
    field_name: str | None,
    prompt: str,
    model: str = DEFAULT_INTERVIEW_MODEL,
    chat_model: object | None = None,
) -> list[str]:
    """Return concrete, domain-tailored example answers for the current question.

    Powers the wizard's "help me figure out" button. Never raises: degrades to
    the field's static examples.

    Args:
        agent_name: Display name of the agent being defined.
        current: The value definition assembled so far.
        field_name: Which field the pending question fills.
        prompt: The pending question text.
        model: A LangChain ``init_chat_model`` identifier.
        chat_model: Optional pre-built chat model (tests).

    Returns:
        Up to a handful of short suggestion strings.
    """
    try:
        return _invoke_suggest(agent_name, current, prompt, model, chat_model)
    except Exception as error:  # noqa: BLE001 - suggestions must never break the wizard
        logger.warning("Value interview suggest failed: %s", error)
        return list(_FALLBACK.get(field_name or "", ("", "", []))[2])


def _meets_minimums(current: ValueContext) -> bool:
    """Whether enough has been captured to allow the interview to end."""
    return bool(
        current.domain
        and current.user_goal
        and len(current.success_criteria) >= MIN_SUCCESS_CRITERIA
        and current.custom_dimensions
    )


def _next_missing_field(current: ValueContext) -> str | None:
    """The first still-incomplete field, in fixed order."""
    if not current.domain:
        return "domain"
    if not current.user_goal:
        return "user_goal"
    if len(current.success_criteria) < MIN_SUCCESS_CRITERIA:
        return "success_criteria"
    if not current.custom_dimensions:
        return "custom_dimensions"
    return None


def _fallback_step(current: ValueContext) -> InterviewStep:
    """Deterministic next question when the model is unavailable."""
    field_name = _next_missing_field(current)
    if field_name is None:
        return _done_step(current)
    prompt, help_text, suggestions = _FALLBACK[field_name]
    return InterviewStep(
        done=False,
        field_name=field_name,
        prompt=prompt,
        help=help_text,
        input_kind=_INPUT_KIND[field_name],
        suggestions=list(suggestions),
    )


def _done_step(current: ValueContext) -> InterviewStep:
    """The terminal step, with a plain recap of what was captured."""
    return InterviewStep(done=True, recap=_recap(current))


def _recap(current: ValueContext) -> str:
    """A short plain-language summary of the assembled definition."""
    parts = []
    if current.domain:
        parts.append(f"a {current.domain} agent")
    if current.user_goal:
        parts.append(f"whose users want to {current.user_goal}")
    pieces = " ".join(parts) or "this agent"
    return (
        f"Value for {pieces} will be judged on "
        f"{len(current.success_criteria)} success criteria and "
        f"{len(current.custom_dimensions)} custom dimension(s)."
    )


def _invoke_advance(
    agent_name: str,
    transcript: list[InterviewTurn],
    current: ValueContext,
    model: str,
    chat_model: object | None,
) -> InterviewStep:
    """One structured-output call for the next step, normalized."""
    from ._schema import InterviewStepSchema

    chat_model = chat_model or _init_model(model)
    structured = chat_model.with_structured_output(InterviewStepSchema)  # type: ignore[attr-defined]
    result = structured.invoke(_advance_messages(agent_name, transcript, current))
    data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    return _normalize_step(data, current)


def _invoke_suggest(
    agent_name: str, current: ValueContext, prompt: str, model: str, chat_model: object | None
) -> list[str]:
    """One structured-output call for suggestions."""
    from ._schema import SuggestionsSchema

    chat_model = chat_model or _init_model(model)
    structured = chat_model.with_structured_output(SuggestionsSchema)  # type: ignore[attr-defined]
    result = structured.invoke(_suggest_messages(agent_name, current, prompt))
    data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    return [str(item) for item in (data.get("suggestions") or [])][:6]


def _init_model(model: str) -> object:
    """Build a chat model lazily (kept out of the base install)."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(model, temperature=0.2)


def _normalize_step(data: dict, current: ValueContext) -> InterviewStep:
    """Coerce raw model output into a valid step (fix field / input kind)."""
    if data.get("done"):
        return InterviewStep(done=True, recap=str(data.get("recap") or _recap(current)))
    field_name = data.get("field")
    if field_name not in _FIELDS:
        field_name = _next_missing_field(current) or "custom_dimensions"
    return InterviewStep(
        done=False,
        field_name=field_name,
        prompt=str(data.get("prompt") or _FALLBACK[field_name][0]),
        help=str(data.get("help") or _FALLBACK[field_name][1]),
        input_kind=_INPUT_KIND[field_name],
        suggestions=[str(item) for item in (data.get("suggestions") or [])][:6],
    )


def _advance_messages(
    agent_name: str, transcript: list[InterviewTurn], current: ValueContext
) -> list[dict[str, str]]:
    """Build the chat messages for an advance call."""
    system = (
        "You help a non-technical manager define how to measure the value their AI agent "
        "delivers — in their own words, for their own domain. Run a short adaptive "
        "interview, ONE question at a time. Using what they have told you, ask the single "
        "most useful next question to complete the picture: the domain the agent works in "
        "(field 'domain'), the goal a conversation should achieve for the user "
        "('user_goal'), the concrete success criteria that mark a good outcome "
        "('success_criteria'), and the custom qualities worth scoring 0-10 "
        "('custom_dimensions'). Make every question specific to their domain and easy to "
        "answer, and propose concrete example answers in 'suggestions'. Keep it short: set "
        "done=true once you have the domain, the user goal, at least two success criteria, "
        "and at least one dimension — or after about eight questions — and write a "
        "one-paragraph plain-language recap."
    )
    user = f"Agent: {agent_name}\n\n{_format_current(current)}\n\n{_format_transcript(transcript)}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _suggest_messages(agent_name: str, current: ValueContext, prompt: str) -> list[dict[str, str]]:
    """Build the chat messages for a suggest call."""
    system = (
        "Suggest 3-5 concrete, domain-specific example answers to the manager's current "
        "question, as short phrases they can pick from. Tailor them to the agent's domain "
        "and what they have already told you."
    )
    user = f"Agent: {agent_name}\n\n{_format_current(current)}\n\nCurrent question: {prompt}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _format_current(current: ValueContext) -> str:
    """Render the partial definition for the model."""
    lines = ["Definition so far:"]
    lines.append(f"- Domain: {current.domain or '(not set)'}")
    lines.append(f"- User goal: {current.user_goal or '(not set)'}")
    crit = "; ".join(current.success_criteria) or "(none yet)"
    lines.append(f"- Success criteria: {crit}")
    dims = ", ".join(current.custom_dimensions) or "(none yet)"
    lines.append(f"- Custom dimensions: {dims}")
    return "\n".join(lines)


def _format_transcript(transcript: list[InterviewTurn]) -> str:
    """Render the answered questions for the model."""
    if not transcript:
        return "No questions answered yet. Ask the first question."
    blocks = [f"Q: {turn.prompt}\nA: {turn.answer}" for turn in transcript]
    return "Answered so far:\n\n" + "\n\n".join(blocks)


def context_from_payload(raw: dict | None) -> ValueContext:
    """Build a :class:`ValueContext` from a wizard request body."""
    raw = raw or {}
    return ValueContext(
        domain=raw.get("domain") or None,
        user_goal=raw.get("user_goal") or None,
        success_criteria=[str(item) for item in raw.get("success_criteria") or []],
        custom_dimensions={
            str(key): str(val) for key, val in (raw.get("custom_dimensions") or {}).items()
        },
    )


def step_to_dict(step: InterviewStep) -> dict:
    """Serialize a step for the JSON response."""
    return {
        "done": step.done,
        "field": step.field_name,
        "prompt": step.prompt,
        "help": step.help,
        "input_kind": step.input_kind,
        "suggestions": list(step.suggestions),
        "recap": step.recap,
    }


def turns_from_payload(raw: list | None) -> list[InterviewTurn]:
    """Build interview turns from a wizard request body."""
    turns = []
    for item in raw or []:
        if isinstance(item, dict):
            turns.append(
                InterviewTurn(
                    field_name=str(item.get("field") or ""),
                    prompt=str(item.get("prompt") or ""),
                    answer=str(item.get("answer") or ""),
                )
            )
    return turns
