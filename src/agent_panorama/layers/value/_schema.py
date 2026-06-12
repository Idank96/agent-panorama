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
