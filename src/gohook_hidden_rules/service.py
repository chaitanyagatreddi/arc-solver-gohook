"""Orchestration layer with explicit integration seams for GoHook."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence
from urllib.parse import urlparse

import xml.etree.ElementTree as ET

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
    if body == "[deleted]" or post.get("author") == "[deleted]":
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
        status=status, removed_by=removed_by, has_link=bool(_link_domain(post)),
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


ATOM = "{http://www.w3.org/2005/Atom}"


def posts_from_rss(subreddit: str, feed_xml: str) -> list[PostFacts]:
    """Public RSS entries. Removal labels are not in this feed, so first sightings stay pending."""
    try:
        root = ET.fromstring(feed_xml)
    except ET.ParseError:
        return []
    posts = []
    for entry in root.findall(f"{ATOM}entry"):
        raw_id = entry.findtext(f"{ATOM}id") or ""
        post_id = raw_id.removeprefix("t3_")
        updated = entry.findtext(f"{ATOM}updated")
        link = entry.find(f"{ATOM}link")
        href = link.get("href") if link is not None else ""
        host = urlparse(href).hostname or ""
        author = (entry.findtext(f"{ATOM}author/{ATOM}name") or "").removeprefix("/u/")
        if not post_id or not updated:
            continue
        posts.append(PostFacts(
            reddit_post_id=post_id,
            subreddit=subreddit.lower(),
            created_utc=datetime.fromisoformat(updated),
            status="skip" if author == "[deleted]" else "stayed",
            has_link=bool(host) and not host.endswith("reddit.com"),
            title_length=len(entry.findtext(f"{ATOM}title") or ""),
            link_domain=host.removeprefix("www.") if host and not host.endswith("reddit.com") else None,
        ))
    return posts


def post_from_fetchlayer(subreddit: str, item: dict) -> PostFacts | None:
    """Map one FetchLayer community post onto the learner columns."""
    post_id = item.get("id")
    created_at = item.get("createdAt")
    if not post_id or not created_at:
        return None
    category = item.get("removedByCategory")
    author = item.get("author")
    deleted = author in (None, "[deleted]", "deleted") or category == "deleted"
    status, removed_by = classify_removal({
        "author": "[deleted]" if deleted else author,
        "removed_by_category": None if category in (None, "deleted") else category,
        "selftext": "",
    })
    domain = str(item.get("domain") or "").lower()
    external = bool(domain) and not domain.startswith("self.") and not domain.endswith("reddit.com")
    return PostFacts(
        reddit_post_id=str(post_id),
        subreddit=subreddit.lower(),
        created_utc=datetime.fromisoformat(created_at.replace("Z", "+00:00")),
        status=status,
        removed_by=removed_by,
        has_link=external,
        link_domain=domain.removeprefix("www.") if external else None,
        title_length=len(str(item.get("title") or "")),
        flair=item.get("flair"),
    )


def sidebar_text(payload: dict) -> str:
    """Written rules only, in the community's own order."""
    lines = []
    for rule in payload.get("rules") or []:
        title = str(rule.get("title") or "").strip()
        if not title:
            continue
        number = rule.get("number")
        lines.append(f"{number}. {title}" if number else title)
        body = str(rule.get("descriptionText") or "").strip()
        if body:
            lines.append(body)
        lines.append("")
    return "\n".join(lines).strip()


async def fetch_sidebar(subreddit: str) -> str:
    import os
    token = os.getenv("FETCHLAYER_TOKEN")
    if not token:
        raise RuntimeError("FETCHLAYER_TOKEN is not set")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.fetchlayer.dev/reddit/community-details",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"subreddit": subreddit},
        )
        response.raise_for_status()
    return sidebar_text(response.json())


async def collect_fetchlayer_posts(subreddit: str, limit: int = 25) -> list[PostFacts]:
    """One FetchLayer page of new posts. The token stays in the environment."""
    import os
    token = os.getenv("FETCHLAYER_TOKEN")
    if not token:
        raise RuntimeError("FETCHLAYER_TOKEN is not set")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.fetchlayer.dev/reddit/community-posts",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"subreddit": subreddit, "sort": "new", "limit": limit},
        )
        response.raise_for_status()
    posts = []
    for item in response.json().get("items") or []:
        post = post_from_fetchlayer(subreddit, item)
        if post is not None:
            posts.append(post)
    return posts


async def collect_public_rss(subreddit: str, limit: int = 25) -> list[PostFacts]:
    """One public RSS page. JSON listing is blocked from this network."""
    headers = {"User-Agent": "python:arc-solver-gohook:0.1 (read-only)"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        response = await client.get(f"https://www.reddit.com/r/{subreddit}/new.rss", params={"limit": limit})
        response.raise_for_status()
    return posts_from_rss(subreddit, response.text)


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
            status = post.status if post.status == "skip" else "pending"
            staged.append(replace(post, status=status, removed_by=post.removed_by if status == "skip" else None, first_seen_at=now))
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


def pipeline_counts(posts: Sequence[PostFacts]) -> dict[str, int]:
    """Operator counts. Failures are counted by the job, not from stored posts."""
    return {
        "collected": len(posts),
        "pending": sum(post.status == "pending" for post in posts),
        "rechecked": sum(post.rechecked_at is not None for post in posts),
        "removed": sum(post.status == "removed" for post in posts),
        "stayed": sum(post.status == "stayed" for post in posts),
        "skipped": sum(post.status == "skip" for post in posts),
    }


async def run_collection(store: Store, subreddits: Sequence[str], fetch, limit: int = 300) -> dict:
    """Collect every tracked subreddit. One failure does not stop the rest."""
    results = []
    for name in subreddits:
        try:
            staged = await collect_and_stage(store, name, limit=limit, fetch=fetch)
            results.append({"subreddit": name, "ok": True, **pipeline_counts(staged)})
        except Exception as exc:
            results.append({"subreddit": name, "ok": False, "error": type(exc).__name__})
    return {
        "subreddits": results,
        "failed": sum(not row["ok"] for row in results),
        "collected": sum(row.get("collected", 0) for row in results),
    }


async def collect_and_stage(store: Store, subreddit: str, limit: int = 300, fetch=None) -> list[PostFacts]:
    """Fetch current posts and persist only initial pending observations or due rechecks."""
    known = await store.posts(subreddit)
    observed = await (fetch or collect_public_posts)(subreddit, limit)
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
