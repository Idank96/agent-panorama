"""The canonical value ontology: the small comparable layer beneath each
customer's own value definition.

Two-layer design (see ``business/strategy/2026-06-07_value-ontology-v0.md``):
the customer writes value in their own words (a :class:`ValueContext`); this
module maps that freeform definition onto a small, stable canonical layer — an
agent *archetype* and a set of value *primitives* — with one LLM call at config
time. The canonical layer is invisible to the customer except as a read-only
"how you compare" surface; it is never authored by hand (manual mapping is the
self-serve friction the moat thesis explicitly avoids).

Never raises: with no provider/key the mapping degrades to ``unknown`` so the
customer still gets their own report, just excluded from any benchmark.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from .context import ValueContext
from .prompts import format_context

logger = logging.getLogger(__name__)

# Mapping is a light classification, so it defaults to the cheapest tier; the
# server overrides it with the configured summarize model (same provider path
# as the summary/judge layers — no new extra).
DEFAULT_MAP_MODEL = "google_genai:gemini-2.5-flash-lite"

# Coarse on purpose (≤8 + unknown). An agent gets exactly one.
ARCHETYPES: dict[str, str] = {
    "support": "resolves a user's issue or question (customer support, helpdesk, IT)",
    "sales": "qualifies, books, or advances a deal (SDR, outreach, lead-gen)",
    "research": "gathers and synthesizes information into an answer or report",
    "tutor": "teaches or coaches a person toward understanding or a skill",
    "coding": "writes, reviews, or debugs software",
    "ops": "executes a back-office task to completion (claims, scheduling, data entry)",
    "assistant": "general personal or work assistant spanning ad-hoc tasks",
    "content": "produces creative, marketing, or written artifacts",
    "unknown": "unclassified",
}

# The comparable value axes, scored 0-10 elsewhere; here they are the targets a
# customer dimension or success criterion maps onto.
PRIMITIVES: dict[str, str] = {
    "goal_completion": "did the user's goal get achieved",
    "response_quality": "accuracy, clarity, and depth of the responses",
    "efficiency": "value delivered relative to the user's effort and turns",
    "autonomy": "finished without handing off to a human",
    "reliability": "worked without rework or retries",
    "safety_trust": "no confidently-wrong, harmful, or policy-violating output",
    "timeliness": "speed to the outcome",
}

# Normalized outcome and value-loss vocabularies — the rest of the canonical
# ontology spec, kept here as the single source of the shared rule-set even
# though per-judgment tagging against them is a deferred follow-up.
OUTCOMES: dict[str, str] = {
    "resolved": "the user's goal was achieved",
    "partial": "the goal was only partially met",
    "failed": "the goal was not achieved",
    "escalated": "handed to a human",
    "abandoned": "the user disengaged or gave up",
    "unknown": "outcome unclear",
}

VALUE_LOSS_MODES: dict[str, str] = {
    "unnecessary_escalation": "handed to a human when it could have resolved",
    "wrong_answer_confident": "incorrect or hallucinated answer stated with confidence",
    "redundant_questions": "asked for info the user already provided",
    "incomplete_resolution": "left the goal partially done",
    "excessive_effort": "too many turns or retries for the outcome",
    "abandonment_risk": "friction or frustration; user likely to give up",
    "missing_followthrough": "claimed an action it did not actually complete",
    "out_of_scope_refusal": "declined something it should have handled",
    "latency_friction": "too slow to be useful",
    "tone_empathy_failure": "tone or empathy miss",
    "other": "unmatched (a signal to grow the taxonomy)",
}

UNKNOWN_ARCHETYPE = "unknown"
MIN_ARCHETYPE_CONFIDENCE = 0.4


@dataclass
class AgentMapping:
    """How one agent's customer-defined value maps onto the canonical layer.

    Produced by :func:`build_agent_mapping`. ``source`` records provenance:
    ``"llm"`` (auto-mapped), ``"manual"`` (a human override in the sidecar), or
    ``"default"`` (degraded — no provider, empty context, or a failed call).
    """

    agent_key: str
    archetype: str = UNKNOWN_ARCHETYPE
    archetype_confidence: float = 0.0
    dimension_to_primitive: dict[str, str] = field(default_factory=dict)
    criterion_to_primitive: dict[str, str] = field(default_factory=dict)
    source: str = "default"


def context_hash(context: ValueContext | None) -> str:
    """Return a stable short hash of a value context, for cache keying.

    Args:
        context: The customer's value definition, or None.

    Returns:
        A 16-char hex digest; empty contexts hash to a fixed sentinel so a
        mapping is only rebuilt when the definition actually changes.
    """
    if _context_is_empty(context):
        return "empty"
    assert context is not None
    payload = json.dumps(
        {
            "domain": context.domain,
            "user_goal": context.user_goal,
            "success_criteria": sorted(context.success_criteria),
            "custom_dimensions": dict(sorted(context.custom_dimensions.items())),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _context_is_empty(context: ValueContext | None) -> bool:
    """Whether a context carries no signal to map (so mapping is skipped)."""
    if context is None:
        return True
    return not (
        context.domain or context.user_goal or context.success_criteria or context.custom_dimensions
    )


def build_agent_mapping(
    agent_key: str,
    context: ValueContext | None,
    model: str = DEFAULT_MAP_MODEL,
    chat_model: object | None = None,
) -> AgentMapping:
    """Map one agent's value context onto the canonical ontology via the LLM.

    Never raises: an empty context, a missing provider/key, or any model error
    degrades to a ``source="default"`` mapping with ``archetype="unknown"``, so
    the customer's own report is unaffected.

    Args:
        agent_key: The agent's slugified name.
        context: The customer's value definition for this agent, or None.
        model: A LangChain ``init_chat_model`` identifier.
        chat_model: Optional pre-built chat model (used by tests); when given,
            ``model`` is informational only.

    Returns:
        The resolved :class:`AgentMapping`.
    """
    if _context_is_empty(context):
        return AgentMapping(agent_key=agent_key)
    assert context is not None
    try:
        return _invoke_mapping(agent_key, context, model, chat_model)
    except Exception as error:  # noqa: BLE001 - mapping must never break a report
        logger.warning("Value mapping for %s with %s failed: %s", agent_key, model, error)
        return AgentMapping(agent_key=agent_key)


def _invoke_mapping(
    agent_key: str, context: ValueContext, model: str, chat_model: object | None
) -> AgentMapping:
    """Call the model with structured output and normalize it to a mapping."""
    from ._schema import AgentMappingSchema

    if chat_model is None:
        from langchain.chat_models import init_chat_model

        chat_model = init_chat_model(model, temperature=0)
    structured = chat_model.with_structured_output(AgentMappingSchema)  # type: ignore[attr-defined]
    result = structured.invoke(_mapping_messages(context))
    data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    return _normalize_mapping(agent_key, data)


def _normalize_mapping(agent_key: str, data: dict) -> AgentMapping:
    """Coerce raw model output into a valid mapping (drop unknown targets)."""
    archetype = data.get("archetype")
    if archetype not in ARCHETYPES:
        archetype = UNKNOWN_ARCHETYPE
    confidence = _clamp_confidence(data.get("archetype_confidence"))
    if confidence < MIN_ARCHETYPE_CONFIDENCE:
        archetype = UNKNOWN_ARCHETYPE
    return AgentMapping(
        agent_key=agent_key,
        archetype=archetype,
        archetype_confidence=confidence,
        dimension_to_primitive=_only_primitives(data.get("dimension_to_primitive")),
        criterion_to_primitive=_only_primitives(data.get("criterion_to_primitive")),
        source="llm",
    )


def _clamp_confidence(value: object) -> float:
    """Clamp a model-provided confidence into [0, 1], defaulting to 0."""
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _only_primitives(raw: object) -> dict[str, str]:
    """Keep only mapping entries whose target is a known primitive key."""
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(val) for key, val in raw.items() if val in PRIMITIVES}


def _mapping_messages(context: ValueContext) -> list[dict[str, str]]:
    """Build the chat messages for the mapping call."""
    archetypes = "\n".join(f"- {key}: {desc}" for key, desc in ARCHETYPES.items())
    primitives = "\n".join(f"- {key}: {desc}" for key, desc in PRIMITIVES.items())
    system = (
        "You map a customer's freeform definition of agent value onto a small, fixed "
        "canonical ontology so different agents can be compared. Choose exactly one "
        "archetype from the allowed list (use 'unknown' only when it is truly "
        "unclassifiable). For each custom dimension and each success criterion, choose "
        "the single closest value primitive from the allowed list. Set "
        "archetype_confidence between 0 and 1.\n\n"
        f"Allowed archetypes:\n{archetypes}\n\nAllowed value primitives:\n{primitives}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": format_context(context)},
    ]


def mapping_to_dict(mapping: AgentMapping) -> dict:
    """Serialize a mapping for the JSON contract / sidecar."""
    return {
        "agent_key": mapping.agent_key,
        "archetype": mapping.archetype,
        "archetype_description": ARCHETYPES.get(mapping.archetype, ""),
        "archetype_confidence": mapping.archetype_confidence,
        "dimension_to_primitive": dict(mapping.dimension_to_primitive),
        "criterion_to_primitive": dict(mapping.criterion_to_primitive),
        "source": mapping.source,
    }


def mapping_from_dict(raw: dict) -> AgentMapping:
    """Rebuild a mapping from its serialized form (sidecar load)."""
    return AgentMapping(
        agent_key=str(raw.get("agent_key") or ""),
        archetype=str(raw.get("archetype") or UNKNOWN_ARCHETYPE),
        archetype_confidence=_clamp_confidence(raw.get("archetype_confidence")),
        dimension_to_primitive=_only_primitives(raw.get("dimension_to_primitive")),
        criterion_to_primitive=_only_primitives(raw.get("criterion_to_primitive")),
        source=str(raw.get("source") or "default"),
    )
