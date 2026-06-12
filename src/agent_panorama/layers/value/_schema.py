"""Pydantic schema for the judge's structured output.

This module is the only place pydantic appears, and it is imported lazily (at
judge call time) so the base install never needs it. Pydantic itself arrives
transitively with any langchain provider extra, which the judge requires
anyway — this adds no dependency of its own.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ValueReportSchema(BaseModel):
    """Structured-output contract the judge model must fill."""

    outcome: str = Field(
        description=(
            "What the user actually walked away with, stated in the customer's domain "
            "language (e.g. 'claim submitted with adjuster scheduled', not 'goal achieved')."
        )
    )
    value_delivered: list[str] = Field(
        description=(
            "Concrete moments where the session created value for the user, in domain "
            "terms, each citing evidence from the transcript."
        )
    )
    value_lost: list[str] = Field(
        description=(
            "Concrete moments where value leaked: friction, redundant questions, wrong or "
            "missing answers, extra effort, abandonment risk. Empty if none."
        )
    )
    recommended_fixes: list[str] = Field(
        description=(
            "Specific, actionable changes the builder should make to recover the lost "
            "value. Empty if nothing to fix."
        )
    )
    goal_completion: int = Field(
        ge=0, le=10, description="How fully the user's goal was achieved by the session."
    )
    response_quality: int = Field(
        ge=0, le=10, description="Accuracy, clarity, and depth of the assistant's responses."
    )
    efficiency: int = Field(
        ge=0, le=10, description="Value delivered relative to the user's effort and turns spent."
    )
    overall_score: int = Field(
        ge=0, le=10, description="Holistic judgement of the value the session gave the user."
    )
    rationale: str = Field(
        description="Short explanation of the scores, citing evidence from the transcript."
    )
    custom_scores: dict[str, int] = Field(
        default_factory=dict,
        description="Score 0-10 for each customer-defined dimension, keyed by its exact name.",
    )
    criteria_verdicts: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Whether each customer success criterion was met, keyed by the exact criterion text."
        ),
    )


class AgentMappingSchema(BaseModel):
    """Structured output for mapping a value context onto the canonical ontology."""

    archetype: str = Field(
        description="Exactly one archetype key from the allowed list, or 'unknown'."
    )
    archetype_confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the chosen archetype, from 0 to 1."
    )
    dimension_to_primitive: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Each custom dimension name mapped to the single closest value primitive key."
        ),
    )
    criterion_to_primitive: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Each success criterion text mapped to the single closest value primitive key."
        ),
    )


class InterviewStepSchema(BaseModel):
    """Structured output for one step of the guided value-definition interview."""

    done: bool = Field(
        description="True once the value definition is complete enough to stop asking."
    )
    field: str | None = Field(
        default=None,
        description=(
            "Which part of the definition this question fills: 'domain', 'user_goal', "
            "'success_criteria', or 'custom_dimensions'. Null when done."
        ),
    )
    prompt: str = Field(
        default="",
        description="The single next question to ask the manager, in plain language.",
    )
    help: str = Field(
        default="",
        description="One short line explaining why this matters or how to think about it.",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Optional concrete example answers, tailored to their domain.",
    )
    recap: str = Field(
        default="",
        description="When done, a one-paragraph plain-language recap of the value definition.",
    )


class SuggestionsSchema(BaseModel):
    """Structured output for the 'help me figure out' suggestion list."""

    suggestions: list[str] = Field(
        default_factory=list,
        description="3-5 concrete, domain-specific example answers to the current question.",
    )
