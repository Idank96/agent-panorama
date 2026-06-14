"""Tests for the value-ontology blueprint and the extended ValueContext."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from agent_panorama.config import value_config_from_dict, value_config_to_dict  # noqa: E402
from agent_panorama.layers.value.blueprint import (  # noqa: E402
    COMPLETE,
    MISSING,
    SUGGESTED,
    THIN,
    VALUE_BLUEPRINT,
    next_gap,
    object_status,
    required_complete,
    serialize_blueprint,
)
from agent_panorama.layers.value.context import ValueContext  # noqa: E402
from agent_panorama.layers.value.prompts import format_context  # noqa: E402


def _full() -> ValueContext:
    return ValueContext(
        domain="support",
        served_user="a frustrated customer",
        user_goal="resolve the billing issue",
        success_criteria=["resolved", "no repeat contact"],
        custom_dimensions={"empathy": "warmth"},
        failure_modes=["wrong refund amount"],
        stakes_good="saves 15 min",
        stakes_bad="triggers a chargeback",
    )


def test_blueprint_has_seven_objects_with_unique_layout() -> None:
    keys = [spec.key for spec in VALUE_BLUEPRINT]
    assert len(keys) == 7
    assert len(set(keys)) == 7
    coords = {spec.layout for spec in VALUE_BLUEPRINT}
    assert len(coords) == 7  # no two objects overlap on the graph


def test_next_gap_walks_required_then_recommended() -> None:
    # Empty context -> first required gap is the domain.
    gap = next_gap(ValueContext())
    assert gap is not None
    assert gap.object_key == "agent"
    assert gap.field_name == "domain"
    assert gap.importance == "required"

    # Required filled -> the next gap is a recommended object, not None.
    required_only = ValueContext(
        domain="support",
        user_goal="resolve",
        success_criteria=["a", "b"],
        custom_dimensions={"empathy": "warmth"},
    )
    assert required_complete(required_only) is True
    rec = next_gap(required_only)
    assert rec is not None
    assert rec.importance == "recommended"

    # Everything filled -> no gap.
    assert next_gap(_full()) is None


def test_success_criteria_minimum_makes_it_thin_then_complete() -> None:
    one = ValueContext(domain="x", user_goal="y", success_criteria=["only one"])
    status = {s.key: s for s in object_status(one)}
    assert status["success_criteria"].state == THIN  # below min_count of 2
    assert status["value_dimensions"].state == MISSING  # required, empty

    full = {s.key: s for s in object_status(_full())}
    assert full["success_criteria"].state == COMPLETE
    assert full["value_dimensions"].state == COMPLETE


def test_recommended_objects_are_suggested_when_empty() -> None:
    status = {s.key: s for s in object_status(ValueContext(domain="x"))}
    assert status["user"].state == SUGGESTED
    assert status["failure_modes"].state == SUGGESTED
    assert status["stakes"].state == SUGGESTED


def test_object_status_summary_describes_contents() -> None:
    status = {s.key: s for s in object_status(_full())}
    assert "support" in status["agent"].summary
    assert "2" in status["success_criteria"].summary  # "2 success criteria"


def test_serialize_blueprint_is_frontend_ready() -> None:
    data = serialize_blueprint()
    agent = next(o for o in data if o["key"] == "agent")
    assert agent["layout"] == {"col": 1, "row": 0}
    assert agent["links"] == [{"to": "user", "relation": "serves"}]
    assert agent["properties"][0]["kind"] == "text"


def test_extended_context_round_trips_through_config() -> None:
    raw = {
        "default": {
            "domain": "support",
            "served_user": "a customer",
            "user_goal": "resolve",
            "success_criteria": ["a"],
            "custom_dimensions": {"empathy": "warmth"},
            "failure_modes": ["wrong amount"],
            "stakes_good": "saves time",
            "stakes_bad": "chargeback",
        },
        "contexts": {},
    }
    config = value_config_from_dict(raw)
    assert config is not None
    again = value_config_from_dict(value_config_to_dict(config))
    assert again == config
    assert config.default is not None
    assert config.default.failure_modes == ["wrong amount"]


def test_old_flat_config_still_loads() -> None:
    raw = {"default": {"domain": "support", "user_goal": "resolve"}, "contexts": {}}
    config = value_config_from_dict(raw)
    assert config is not None
    assert config.default is not None
    assert config.default.failure_modes == []  # new field defaults empty
    assert config.default.served_user is None


def test_judge_prompt_includes_new_fields() -> None:
    rendered = format_context(_full())
    assert "User served: a frustrated customer" in rendered
    assert "Failure mode to watch for: wrong refund amount" in rendered
    assert "A good conversation is worth: saves 15 min" in rendered
    assert "A bad conversation costs: triggers a chargeback" in rendered


def test_merged_over_fills_new_fields_from_base() -> None:
    base = ValueContext(domain="support", failure_modes=["base mode"], stakes_good="base worth")
    override = ValueContext(user_goal="resolve")
    merged = override.merged_over(base)
    assert merged.domain == "support"
    assert merged.failure_modes == ["base mode"]
    assert merged.stakes_good == "base worth"
    assert merged.user_goal == "resolve"
