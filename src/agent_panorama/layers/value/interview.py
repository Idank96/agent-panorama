"""The guided value-definition interview: a blueprint-driven, one-question-at-a-
time discovery flow that helps a non-technical manager fill in the value-ontology
map (see ``blueprint.py``) for their agent.

The blueprint decides *what* to ask next — ``next_gap`` returns the most important
still-missing object property, so coverage of the full picture is guaranteed and
the interview implicitly asks for whatever the manager has not yet provided. The
LLM only does the intelligent part: phrasing that question for their domain and
proposing example answers.

Stateless by design: the caller (the live server, on behalf of the dashboard
wizard) holds the transcript and the partial :class:`ValueContext`. Mirrors the
rest of the value layer: lazy pydantic in ``_schema.py``, the same
``init_chat_model`` provider path, and it **never raises** — any error or missing
provider degrades to the gap's deterministic default question.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .blueprint import VALUE_BLUEPRINT, Gap, next_gap
from .context import ValueContext

logger = logging.getLogger(__name__)

# Same cheap tier as the mapping layer; the server passes its summarize model.
DEFAULT_INTERVIEW_MODEL = "google_genai:gemini-2.5-flash-lite"

# Safety cap: required objects are always asked, but recommended ones stop being
# offered past this many questions so the interview never drags.
MAX_QUESTIONS = 10

# Default question phrasing per field, used when no model is available.
_DEFAULT_PROMPTS = {
    "domain": "What does this agent help your users do, and in what setting?",
    "served_user": "Who is on the other end of these conversations, and what's their situation?",
    "user_goal": "What is a user trying to achieve when they talk to this agent?",
    "success_criteria": "What marks a genuinely good outcome? Add a few concrete checks.",
    "custom_dimensions": "What qualities should every conversation be scored on, 0-10?",
    "failure_modes": "What does it look like when this agent gets it wrong?",
    "stakes_good": "When a conversation goes well, what is that worth to you?",
    "stakes_bad": "When a conversation goes badly, what does it cost you?",
}

_EXAMPLES = {prop.key: list(prop.examples) for spec in VALUE_BLUEPRINT for prop in spec.properties}


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
    object_key: str = ""
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

    The blueprint's :func:`next_gap` chooses the object/property to ask about;
    the LLM phrases it. Never raises: a missing provider/key or any model error
    degrades to the gap's default question.

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
    gap = next_gap(current)
    if gap is None:
        return _done_step(current)
    if gap.importance == "recommended" and len(transcript) >= MAX_QUESTIONS:
        return _done_step(current)
    try:
        return _invoke_advance(agent_name, transcript, current, gap, model, chat_model)
    except Exception as error:  # noqa: BLE001 - the wizard must always advance
        logger.warning("Value interview advance failed: %s", error)
        return _gap_step(gap)


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
        return list(_EXAMPLES.get(field_name or "", []))


def _gap_step(gap: Gap) -> InterviewStep:
    """The deterministic step for a gap when the model is unavailable."""
    return InterviewStep(
        done=False,
        field_name=gap.field_name,
        object_key=gap.object_key,
        prompt=_DEFAULT_PROMPTS.get(gap.field_name, f"Tell me about: {gap.label}"),
        help=gap.help,
        input_kind=gap.kind,
        suggestions=list(gap.examples),
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
    who = " ".join(parts) or "this agent"
    measures = [
        f"{len(current.success_criteria)} success criteria",
        f"{len(current.custom_dimensions)} value dimension(s)",
    ]
    if current.failure_modes:
        measures.append(f"{len(current.failure_modes)} failure mode(s)")
    if current.stakes_good or current.stakes_bad:
        measures.append("the stakes")
    return f"Value for {who} will be judged on " + ", ".join(measures) + "."


def _invoke_advance(
    agent_name: str,
    transcript: list[InterviewTurn],
    current: ValueContext,
    gap: Gap,
    model: str,
    chat_model: object | None,
) -> InterviewStep:
    """One structured-output call to phrase the gap's question, normalized."""
    from ._schema import InterviewStepSchema

    chat_model = chat_model or _init_model(model)
    structured = chat_model.with_structured_output(InterviewStepSchema)  # type: ignore[attr-defined]
    result = structured.invoke(_advance_messages(agent_name, transcript, current, gap))
    data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    return _step_from_model(data, gap)


def _step_from_model(data: dict, gap: Gap) -> InterviewStep:
    """Combine the model's phrasing with the gap's fixed target."""
    suggestions = [str(item) for item in (data.get("suggestions") or [])][:6]
    return InterviewStep(
        done=False,
        field_name=gap.field_name,
        object_key=gap.object_key,
        prompt=str(data.get("prompt") or _DEFAULT_PROMPTS.get(gap.field_name, gap.label)),
        help=str(data.get("help") or gap.help),
        input_kind=gap.kind,
        suggestions=suggestions or list(gap.examples),
    )


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


def _advance_messages(
    agent_name: str, transcript: list[InterviewTurn], current: ValueContext, gap: Gap
) -> list[dict[str, str]]:
    """Build the chat messages for an advance call directed at one gap."""
    system = (
        "You help a non-technical manager define how to measure the value their AI agent "
        "delivers — in their own words, for their own domain. You are filling a fixed map "
        "of the value definition, one question at a time. You are told which part to ask "
        "about next: phrase ONE clear, friendly question for it, tailored to this agent's "
        "domain and what the manager has already said, and propose 2-4 concrete example "
        "answers in 'suggestions'. Do not ask about anything else, and set done=false — the "
        "system decides when the map is complete."
    )
    user = (
        f"Agent: {agent_name}\n\n"
        f"{_format_current(current)}\n\n"
        f"{_format_transcript(transcript)}\n\n"
        f"Ask about: {gap.label} — {gap.help}"
    )
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
    lines.append(f"- User served: {current.served_user or '(not set)'}")
    lines.append(f"- User goal: {current.user_goal or '(not set)'}")
    lines.append(f"- Success criteria: {'; '.join(current.success_criteria) or '(none yet)'}")
    lines.append(f"- Value dimensions: {', '.join(current.custom_dimensions) or '(none yet)'}")
    lines.append(f"- Failure modes: {'; '.join(current.failure_modes) or '(none yet)'}")
    stakes = "; ".join(filter(None, [current.stakes_good, current.stakes_bad])) or "(not set)"
    lines.append(f"- Stakes: {stakes}")
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
        served_user=raw.get("served_user") or None,
        failure_modes=[str(item) for item in raw.get("failure_modes") or []],
        stakes_good=raw.get("stakes_good") or None,
        stakes_bad=raw.get("stakes_bad") or None,
    )


def step_to_dict(step: InterviewStep) -> dict:
    """Serialize a step for the JSON response."""
    return {
        "done": step.done,
        "field": step.field_name,
        "object_key": step.object_key,
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
