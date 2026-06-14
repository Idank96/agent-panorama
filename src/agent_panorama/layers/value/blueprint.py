"""The value-ontology blueprint: the predefined map of objects a complete value
definition fills in.

Where ``ontology.py`` holds the *canonical* layer (archetypes, primitives), this
module holds the *customer-extension* layer's structure — the fixed set of object
types that, filled together, form the full picture of how an agent's value is
measured: who is served, what they want, how we know it worked, what it is worth,
and how it fails.

The blueprint drives three things off one source of truth: the visual graph
(``layout`` + ``links``), the gap-aware interview (``next_gap`` finds the most
important still-missing object), and completeness reporting (``object_status``).
It reads a :class:`ValueContext` and never mutates it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .context import ValueContext

# Object fill states, worst-to-best for the graph's colour coding.
MISSING = "missing"  # required, empty
THIN = "thin"  # required, present but below its minimum
SUGGESTED = "suggested"  # recommended, empty
COMPLETE = "complete"  # satisfied


@dataclass(frozen=True)
class PropertySpec:
    """One editable property of an object, bound to a :class:`ValueContext` field."""

    key: str  # the ValueContext attribute name
    label: str
    kind: str  # "text" | "longtext" | "list" | "dimensions"
    help: str
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObjectSpec:
    """One object type in the value ontology."""

    key: str
    label: str
    description: str
    importance: str  # "required" | "recommended"
    properties: tuple[PropertySpec, ...]
    links: tuple[tuple[str, str], ...] = ()  # (target_object_key, relation_label)
    layout: tuple[int, int] = (0, 0)  # (column, row) for the graph
    min_count: int = 0  # minimum filled entries for a list/dimensions property


@dataclass
class ObjectStatus:
    """The fill state of one object for a given context."""

    key: str
    state: str
    summary: str
    filled: int = 0


@dataclass
class Gap:
    """The next thing the interview should ask about."""

    object_key: str
    field_name: str
    kind: str
    label: str
    help: str
    examples: list[str] = field(default_factory=list)
    importance: str = "required"


VALUE_BLUEPRINT: tuple[ObjectSpec, ...] = (
    ObjectSpec(
        key="agent",
        label="Agent",
        description="What this agent is and the world it works in.",
        importance="required",
        properties=(
            PropertySpec(
                key="domain",
                label="Domain",
                kind="text",
                help="The world this agent works in — so value is judged in your language.",
                examples=("B2B SaaS billing support", "Internal IT helpdesk"),
            ),
        ),
        links=(("user", "serves"),),
        layout=(1, 0),
    ),
    ObjectSpec(
        key="user",
        label="User",
        description="Who the agent serves and the situation they are in.",
        importance="recommended",
        properties=(
            PropertySpec(
                key="served_user",
                label="Who is served",
                kind="longtext",
                help="The person on the other end and their situation.",
                examples=("A frustrated customer who was charged twice",),
            ),
        ),
        links=(("goal", "wants"),),
        layout=(0, 1),
    ),
    ObjectSpec(
        key="goal",
        label="Goal",
        description="The outcome the user wants from a conversation.",
        importance="required",
        properties=(
            PropertySpec(
                key="user_goal",
                label="What the user is trying to achieve",
                kind="longtext",
                help="Value is judged against this goal, not a generic checklist.",
                examples=("Resolve a billing discrepancy without contacting a human",),
            ),
        ),
        links=(
            ("success_criteria", "measured by"),
            ("value_dimensions", "measured by"),
            ("failure_modes", "threatened by"),
            ("stakes", "worth"),
        ),
        layout=(1, 1),
    ),
    ObjectSpec(
        key="success_criteria",
        label="Success criteria",
        description="Concrete pass/fail checks that mark a good outcome.",
        importance="required",
        properties=(
            PropertySpec(
                key="success_criteria",
                label="Success criteria",
                kind="list",
                help="Each is reported met / not met for every conversation.",
                examples=("Refund processed", "No repeat contact within 48h"),
            ),
        ),
        layout=(0, 2),
        min_count=2,
    ),
    ObjectSpec(
        key="value_dimensions",
        label="Value dimensions",
        description="Named qualities every conversation is scored on, 0-10.",
        importance="required",
        properties=(
            PropertySpec(
                key="custom_dimensions",
                label="Custom value dimensions",
                kind="dimensions",
                help="Qualities that matter to you beyond a simple pass/fail.",
                examples=("empathy", "first-contact resolution"),
            ),
        ),
        layout=(1, 2),
        min_count=1,
    ),
    ObjectSpec(
        key="failure_modes",
        label="Failure modes",
        description="What going wrong looks like in your domain.",
        importance="recommended",
        properties=(
            PropertySpec(
                key="failure_modes",
                label="Failure modes",
                kind="list",
                help="The ways this agent loses value — used to spot leaks.",
                examples=("Tells a customer the wrong refund amount", "Escalates avoidably"),
            ),
        ),
        layout=(2, 2),
        min_count=1,
    ),
    ObjectSpec(
        key="stakes",
        label="Stakes",
        description="What a good conversation is worth and a bad one costs.",
        importance="recommended",
        properties=(
            PropertySpec(
                key="stakes_good",
                label="What a good conversation is worth",
                kind="longtext",
                help="The upside — saved cost, retained revenue, time back.",
                examples=("Saves ~15 min of agent time and avoids a churn risk",),
            ),
            PropertySpec(
                key="stakes_bad",
                label="What a bad conversation costs",
                kind="longtext",
                help="The downside — escalation cost, lost trust, churn.",
                examples=("A wrong answer can trigger a chargeback and a complaint",),
            ),
        ),
        links=(),
        layout=(2, 1),
    ),
)


def _value_of(context: ValueContext, key: str) -> object:
    """Read a property's value off the context."""
    return getattr(context, key, None)


def _filled_count(value: object) -> int:
    """How many entries a property holds (1 for a non-empty scalar)."""
    if isinstance(value, (list, dict)):
        return len([item for item in value if item])
    return 1 if value else 0


def _property_satisfied(spec: ObjectSpec, prop: PropertySpec, context: ValueContext) -> bool:
    """Whether one property meets its minimum for the object."""
    count = _filled_count(_value_of(context, prop.key))
    if prop.kind in ("list", "dimensions"):
        return count >= max(spec.min_count, 1)
    return count >= 1


def object_status(context: ValueContext) -> list[ObjectStatus]:
    """Report the fill state of every object for a context.

    Args:
        context: The value definition to inspect.

    Returns:
        One :class:`ObjectStatus` per blueprint object, in blueprint order.
    """
    return [_status_for(spec, context) for spec in VALUE_BLUEPRINT]


def _status_for(spec: ObjectSpec, context: ValueContext) -> ObjectStatus:
    """Compute one object's status."""
    filled = sum(_filled_count(_value_of(context, prop.key)) for prop in spec.properties)
    satisfied = all(_property_satisfied(spec, prop, context) for prop in spec.properties)
    any_filled = filled > 0
    if satisfied and any_filled:
        state = COMPLETE
    elif spec.importance == "required":
        state = THIN if any_filled else MISSING
    else:
        state = COMPLETE if any_filled else SUGGESTED
    return ObjectStatus(key=spec.key, state=state, summary=_summary(spec, context), filled=filled)


def _summary(spec: ObjectSpec, context: ValueContext) -> str:
    """A short human summary of what an object currently holds."""
    pieces = []
    for prop in spec.properties:
        value = _value_of(context, prop.key)
        if isinstance(value, (list, dict)):
            count = _filled_count(value)
            if count:
                pieces.append(f"{count} {prop.label.lower()}")
        elif value:
            text = str(value)
            pieces.append(text if len(text) <= 48 else text[:47] + "…")
    return " · ".join(pieces)


def next_gap(context: ValueContext) -> Gap | None:
    """Return the most important still-missing object property, or None.

    Required objects come first (in blueprint order), then recommended ones —
    this is what lets the interview implicitly ask for whatever the manager has
    not yet provided.

    Args:
        context: The value definition so far.

    Returns:
        The next :class:`Gap`, or None when every required object is satisfied
        and every recommended object has at least been offered (all filled).
    """
    for importance in ("required", "recommended"):
        for spec in VALUE_BLUEPRINT:
            if spec.importance != importance:
                continue
            for prop in spec.properties:
                if not _property_satisfied(spec, prop, context):
                    return _gap(spec, prop)
    return None


def _gap(spec: ObjectSpec, prop: PropertySpec) -> Gap:
    """Build a :class:`Gap` for one object property."""
    return Gap(
        object_key=spec.key,
        field_name=prop.key,
        kind=prop.kind,
        label=prop.label,
        help=prop.help,
        examples=list(prop.examples),
        importance=spec.importance,
    )


def required_complete(context: ValueContext) -> bool:
    """Whether every required object is satisfied."""
    return all(
        all(_property_satisfied(spec, prop, context) for prop in spec.properties)
        for spec in VALUE_BLUEPRINT
        if spec.importance == "required"
    )


def serialize_blueprint() -> list[dict]:
    """Serialize the blueprint for the frontend graph (static, no context)."""
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "description": spec.description,
            "importance": spec.importance,
            "layout": {"col": spec.layout[0], "row": spec.layout[1]},
            "links": [{"to": target, "relation": relation} for target, relation in spec.links],
            "properties": [
                {
                    "key": prop.key,
                    "label": prop.label,
                    "kind": prop.kind,
                    "help": prop.help,
                    "examples": list(prop.examples),
                }
                for prop in spec.properties
            ],
            "min_count": spec.min_count,
        }
        for spec in VALUE_BLUEPRINT
    ]
