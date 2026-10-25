"""A deliberately small, executable rule language.

LLMs may suggest rules but never supply Python or SQL. This module validates and
evaluates the JSON AST stored in `sub_rules.condition`.
"""
from __future__ import annotations

from typing import Any, Mapping

ALLOWED_FIELDS = {
    "has_link", "link_domain", "is_self_promo", "title_length", "flair",
    "author_age_days", "author_karma", "author_sub_comments", "author_posts_today",
}
OPS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "exists"}


class InvalidCondition(ValueError):
    pass


def validate(condition: Mapping[str, Any]) -> None:
    """Reject fields/operators/types that cannot be evaluated deterministically."""
    if not isinstance(condition, Mapping):
        raise InvalidCondition("condition must be an object")
    keys = set(condition)
    if keys == {"all"} or keys == {"any"}:
        children = next(iter(condition.values()))
        if not isinstance(children, list) or not children:
            raise InvalidCondition("all/any need a non-empty list")
        for child in children:
            validate(child)
        return
    if keys == {"not"}:
        validate(condition["not"])
        return
    if keys != {"field", "op", "value"}:
        raise InvalidCondition("leaf must contain exactly field, op, value")
    field, op, value = condition["field"], condition["op"], condition["value"]
    if field not in ALLOWED_FIELDS:
        raise InvalidCondition(f"unknown field: {field}")
    if op not in OPS:
        raise InvalidCondition(f"unknown operator: {op}")
    if op == "in" and (not isinstance(value, list) or not value):
        raise InvalidCondition("in needs a non-empty list")
    if op == "exists" and not isinstance(value, bool):
        raise InvalidCondition("exists needs a boolean value")
    if op in {"lt", "lte", "gt", "gte"} and not isinstance(value, (int, float)):
        raise InvalidCondition(f"{op} needs a number")


def matches(condition: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    validate(condition)
    if "all" in condition:
        return all(matches(c, facts) for c in condition["all"])
    if "any" in condition:
        return any(matches(c, facts) for c in condition["any"])
    if "not" in condition:
        return not matches(condition["not"], facts)

    field, op, expected = condition["field"], condition["op"], condition["value"]
    present, actual = field in facts and facts[field] is not None, facts.get(field)
    if op == "exists":
        return present is expected
    if not present:
        return False
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return actual in expected
    try:
        return {
            "lt": actual < expected,
            "lte": actual <= expected,
            "gt": actual > expected,
            "gte": actual >= expected,
        }[op]
    except TypeError:
        return False


def referenced_fields(condition: Mapping[str, Any]) -> set[str]:
    validate(condition)
    if "all" in condition or "any" in condition:
        return set().union(*(referenced_fields(c) for c in condition.get("all", condition.get("any"))))
    if "not" in condition:
        return referenced_fields(condition["not"])
    return {condition["field"]}
