"""The value layer: judge whether a conversation was worth it for the user.

Absorbed from the standalone ``value-layer`` prototype. The judge scores each
conversation against the customer's own definition of value (a
:class:`ValueContext`), producing a :class:`~agent_panorama.models.ValueJudgment`
— scores 0-10, the moments value was delivered or lost, and actionable fixes.
"""

from .context import ValueContext
from .judge import (
    DEFAULT_JUDGE_MODEL,
    ValueJudgmentExchange,
    exchanges_from_turns,
    judge_session,
)
from .prompts import Exchange, build_judge_messages

__all__ = [
    "DEFAULT_JUDGE_MODEL",
    "Exchange",
    "ValueContext",
    "ValueJudgmentExchange",
    "build_judge_messages",
    "exchanges_from_turns",
    "judge_session",
]
