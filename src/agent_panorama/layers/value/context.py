"""The customer's definition of value: the ontology the judge scores against."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValueContext:
    """Customer-defined value definition for one agent's conversations.

    Value is defined by the customer in their own domain, never by a generic
    rubric: the judge scores goal completion against ``user_goal``, reports a
    pass/fail verdict per ``success_criteria`` entry, and scores every
    ``custom_dimensions`` entry 0-10 under its exact name.
    """

    domain: str | None = None
    user_goal: str | None = None
    success_criteria: list[str] = field(default_factory=list)
    custom_dimensions: dict[str, str] = field(default_factory=dict)

    def merged_over(self, base: ValueContext | None) -> ValueContext:
        """Return this context with empty fields filled from ``base``.

        Args:
            base: The fallback (default) context, or None.

        Returns:
            A new :class:`ValueContext`; this context's fields win field-wise.
        """
        if base is None:
            return self
        return ValueContext(
            domain=self.domain or base.domain,
            user_goal=self.user_goal or base.user_goal,
            success_criteria=self.success_criteria or list(base.success_criteria),
            custom_dimensions=self.custom_dimensions or dict(base.custom_dimensions),
        )
