"""Orchestration layer with explicit integration seams for GoHook."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence
from urllib.parse import urlparse

import httpx

from .learner import SYSTEM_PROMPT, kept_rules, learner_rows, parse_candidates, split_posts
from .models import CandidateRule, EvaluatedRule, PostFacts


class Store(Protocol):
    async def posts(self, subreddit: str) -> Sequence[PostFacts]: ...
    async def save_posts(self, posts: Sequence[PostFacts]) -> None: ...
    async def sidebar_rules(self, subreddit: str) -> str: ...
    async def save_rule(self, subreddit: str, evaluated: EvaluatedRule) -> None: ...
    async def active_rules(self, subreddit: str) -> Sequence[dict]: ...
    async def feedback_wrong(self, rule_id: str, user_id: str, week_start: str) -> int: ...


class RuleProposer(Protocol):
    async def propose(self, system: str, payload: dict) -> str: ...


def _link_domain(post: dict) -> str | None:
    url = str(post.get("url_overridden_by_dest") or post.get("url") or "")
    host = urlparse(url).hostname
    return host.lower().removeprefix("www.") if host else None


def classify_removal(post: dict) -> tuple[str, str | None]:
    """Never classify author deletions or sitewide actions as moderator evidence."""
    removed_by = post.get("removed_by_category")
    body = post.get("selftext")
    if body == "[deleted]" or post.get("author") in (None, "[deleted]"):
        return "skip", None
    if removed_by in {"reddit", "anti_evil_ops"}:
        return "skip", str(removed_by)
    if removed_by or body == "[removed]":
        return "removed", str(removed_by or "unknown")
    return "stayed", None


def post_from_reddit(subreddit: str, post: dict) -> PostFacts:
    status, removed_by = classify_removal(post)
    created = datetime.fromtimestamp(float(post["created_utc"]), tz=timezone.utc)
    return PostFacts(
        reddit_post_id=str(post["id"]),
        subreddit=subreddit.lower(),
        created_utc=created,
        status=status, has_link=bool(_link_domain(post)),
        link_domain=_link_domain(post), title_length=len(str(post.get("title") or "")),
        flair=post.get("link_flair_text"), is_self_promo=None,
        author_age_days=None, author_karma=None, author_sub_comments=None, author_posts_today=None,
    )


async def collect_public_posts(subreddit: str, limit: int = 100) -> list[PostFacts]:
    """Collect public Reddit JSON. Production should prefer Composio when it adds author facts."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    headers = {"User-Agent": "GoHookHiddenRules/0.1 (read-only research)"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        children, after = [], None
        while len(children) < limit:
            response = await client.get(
                url, params={"limit": min(100, limit - len(children)), "raw_json": 1, **({"after": after} if after else {})},
            )
            response.raise_for_status()
            page = response.json().get("data", {})
            children.extend(page.get("children", []))
            after = page.get("after")
            if not after:
                break
    return [post_from_reddit(subreddit, item["data"]) for item in children if item.get("kind") == "t3"]


def due_for_recheck(post: PostFacts, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    seen = post.first_seen_at or post.created_utc
    return post.status == "pending" and timedelta(hours=24) <= now - seen <= timedelta(hours=72)


def stage_observations(existing: Sequence[PostFacts], observed: Sequence[PostFacts],
                       now: datetime | None = None) -> list[PostFacts]:
    """First sightings are pending; only a later observation supplies a removal label."""
    now = now or datetime.now(timezone.utc)
    known = {post.reddit_post_id: post for post in existing}
    staged = []
    for post in observed:
        prior = known.get(post.reddit_post_id)
        if prior is None:
            staged.append(replace(post, status="pending", first_seen_at=now))
        elif due_for_recheck(prior, now):
            staged.append(replace(post, first_seen_at=prior.first_seen_at, rechecked_at=now))
        else:
            staged.append(replace(prior, has_link=post.has_link, link_domain=post.link_domain,
                                  title_length=post.title_length, flair=post.flair))
    return staged


async def learn_subreddit(store: Store, proposer: RuleProposer, subreddit: str) -> list[EvaluatedRule]:
    posts = await store.posts(subreddit)
    learn, test = split_posts(posts, subreddit)
    if sum(p.status == "removed" for p in learn) < 20:
        return []
    response = await proposer.propose(SYSTEM_PROMPT, {
        "subreddit": subreddit, "sidebar_rules": await store.sidebar_rules(subreddit),
        "posts": learner_rows(learn),
    })
    results = kept_rules(parse_candidates(response), test)
    for result in results:
        await store.save_rule(subreddit, result)
    return results


async def collect_and_stage(store: Store, subreddit: str, limit: int = 300) -> list[PostFacts]:
    """Fetch current posts and persist only initial pending observations or due rechecks."""
    known = await store.posts(subreddit)
    observed = await collect_public_posts(subreddit, limit)
    staged = stage_observations(known, observed)
    await store.save_posts(staged)
    return staged


async def matching_warnings(store: Store, subreddit: str, facts: dict) -> list[dict]:
    from .conditions import matches
    warnings = []
    for rule in await store.active_rules(subreddit.lower()):
        if matches(rule["condition"], facts):
            warnings.append({
                "rule_id": rule["id"], "rule_text": rule["rule_text"],
                "correct": rule["correct"], "tested": rule["tested"],
                "learned_at": rule["learned_at"], "tag": "Learned",
            })
    return warnings
