"""Judge prompt assembly: transcript and customer-context formatting."""

from __future__ import annotations

from dataclasses import dataclass

from .context import ValueContext

JUDGE_SYSTEM_PROMPT = (
    "You are an impartial evaluator of LLM sessions. Given a transcript of user/assistant "
    "exchanges, measure how much value the session delivered to the user. Score each "
    "dimension from 0 (no value) to 10 (exceptional value): goal_completion (was the "
    "user's goal achieved), response_quality (accuracy, clarity, depth of the responses), "
    "efficiency (value delivered relative to the user's effort and turns spent). Set "
    "overall_score to your holistic judgement and explain it in a short rationale that "
    "cites concrete evidence from the transcript. Scores alone are not the product: state "
    "the outcome as what the user actually walked away with, list the concrete moments "
    "where value was created (value_delivered) and where it leaked (value_lost), and give "
    "specific recommended_fixes the builder of this system can act on. Cite the transcript "
    "in every item."
)

CONTEXT_PREAMBLE = (
    "Value is defined by the customer, not by a generic rubric. The customer context below "
    "is the definition of value for this session: judge goal_completion against the "
    "customer's stated user goal, judge efficiency against their success criteria, score "
    "every custom dimension from 0 to 10 in custom_scores keyed by its exact name, and "
    "report whether each success criterion was met in criteria_verdicts keyed by the exact "
    "criterion text. Write outcome, value_delivered, value_lost, and recommended_fixes in "
    "the customer's own domain vocabulary, not in generic evaluation language. When the "
    "customer lists their own failure modes, check the transcript for each and surface any "
    "you find in value_lost. When they state the stakes (what a good conversation is worth "
    "and what a bad one costs), weigh those stakes in overall_score — a session that "
    "protects high stakes is worth more than one that does not."
)


@dataclass(frozen=True)
class Exchange:
    """One user/assistant exchange of a conversation, as the judge sees it."""

    user_input: str
    assistant_output: str


def format_transcript(exchanges: list[Exchange]) -> str:
    """Format session exchanges as a numbered transcript for the judge.

    Args:
        exchanges: Ordered user/assistant exchanges from the session.

    Returns:
        The transcript rendered as numbered exchange blocks.
    """
    blocks = [
        f"Exchange {index}:\nUser: {exchange.user_input}\nAssistant: {exchange.assistant_output}"
        for index, exchange in enumerate(exchanges, start=1)
    ]
    return "Session transcript:\n\n" + "\n\n".join(blocks)


def format_context(context: ValueContext) -> str:
    """Render the customer's value definition for the judge prompt.

    Args:
        context: The customer-defined value context.

    Returns:
        The context rendered as labelled bullet lines.
    """
    lines = ["Customer context:"]
    if context.domain:
        lines.append(f"- Domain: {context.domain}")
    if context.served_user:
        lines.append(f"- User served: {context.served_user}")
    if context.user_goal:
        lines.append(f"- User goal: {context.user_goal}")
    lines.extend(f"- Success criterion: {criterion}" for criterion in context.success_criteria)
    lines.extend(
        f"- Custom dimension '{name}': {description}"
        for name, description in context.custom_dimensions.items()
    )
    lines.extend(f"- Failure mode to watch for: {mode}" for mode in context.failure_modes)
    if context.stakes_good:
        lines.append(f"- A good conversation is worth: {context.stakes_good}")
    if context.stakes_bad:
        lines.append(f"- A bad conversation costs: {context.stakes_bad}")
    return "\n".join(lines)


def build_judge_messages(
    exchanges: list[Exchange], context: ValueContext | None = None
) -> list[dict[str, str]]:
    """Build the judge chat messages, contextualized to the customer when provided.

    Args:
        exchanges: Ordered user/assistant exchanges from the session.
        context: Optional customer-defined value context.

    Returns:
        System and user messages for the judge model.
    """
    system = JUDGE_SYSTEM_PROMPT
    user = format_transcript(exchanges)
    if context is not None:
        system = f"{JUDGE_SYSTEM_PROMPT}\n\n{CONTEXT_PREAMBLE}"
        user = f"{format_context(context)}\n\n{user}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
