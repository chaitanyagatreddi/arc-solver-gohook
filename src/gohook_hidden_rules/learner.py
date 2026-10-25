"""Data splitting, LLM candidate parsing, and held-out evaluation."""
from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable, Sequence
from typing import Any

from .conditions import InvalidCondition, matches, validate
from .models import CandidateRule, EvaluatedRule, PostFacts

MAX_CANDIDATES = 5

SYSTEM_PROMPT = """You infer possible *unwritten* subreddit removal rules.
Return JSON only: {"rules":[{"rule_text":"...", "condition":{...}}]}.
The condition must be an AST using only:
- leaves: {"field": FIELD, "op": eq|ne|lt|lte|gt|gte|in|exists, "value": VALUE}
- groups: {"all":[CONDITION,...]}, {"any":[CONDITION,...]}, or {"not": CONDITION}
Allowed FIELD values are has_link, link_domain, is_self_promo, title_length,
flair, author_age_days, author_karma, author_sub_comments, author_posts_today.
Propose at most five rules. Explain removals only; do not copy sidebar rules,
invent a field, make a claim about individual moderators, or include code."""


def split_posts(posts: Sequence[PostFacts], subreddit: str) -> tuple[list[PostFacts], list[PostFacts]]:
    """Stable 70/30 split prevents an LLM from seeing held-out observations."""
    eligible = [p for p in posts if p.status in ("stayed", "removed")]
    rng = random.Random(hashlib.sha256(subreddit.lower().encode()).hexdigest())
    shuffled = eligible[:]
    rng.shuffle(shuffled)
    cut = round(len(shuffled) * 0.70)
    return shuffled[:cut], shuffled[cut:]


def learner_rows(posts: Iterable[PostFacts]) -> list[dict[str, Any]]:
    """Only known facts and the outcome are visible to the model."""
    return [{**p.rule_facts(), "removed": p.status == "removed"} for p in posts]


def parse_candidates(raw: str) -> list[CandidateRule]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("model response was not JSON") from exc
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("model response did not include rules")
    accepted: list[CandidateRule] = []
    seen: set[str] = set()
    for item in rules[:MAX_CANDIDATES]:
        if not isinstance(item, dict) or not isinstance(item.get("rule_text"), str) or not isinstance(item.get("condition"), dict):
            continue
        text = " ".join(item["rule_text"].split())[:500]
        if not text or text.casefold() in seen:
            continue
        try:
            validate(item["condition"])
        except InvalidCondition:
            continue
        seen.add(text.casefold())
        accepted.append(CandidateRule(rule_text=text, condition=item["condition"]))
    return accepted


def evaluate(candidate: CandidateRule, held_out: Iterable[PostFacts]) -> EvaluatedRule:
    """A rule predicts removal whenever its condition applies.

    Accuracy is intentionally measured only among matching examples; applying
    to too few examples or no actual removals cannot pass the gate.
    """
    matched = [p for p in held_out if matches(candidate.condition, p.rule_facts())]
    removed = sum(p.status == "removed" for p in matched)
    return EvaluatedRule(candidate=candidate, correct=removed, tested=len(matched), removed_matches=removed)


def kept_rules(candidates: Iterable[CandidateRule], held_out: Iterable[PostFacts]) -> list[EvaluatedRule]:
    test = list(held_out)
    return [result for candidate in candidates if (result := evaluate(candidate, test)).eligible]
