"""Supabase persistence adapter matching GoHook's existing REST pattern."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Sequence

import httpx

from .models import EvaluatedRule, PostFacts


class SupabaseStore:
    def __init__(self, url: str, service_role_key: str):
        self.url = url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {service_role_key}", "apikey": service_role_key,
            "Content-Type": "application/json",
        }

    async def _get(self, table: str, **params) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.url}/rest/v1/{table}", headers=self.headers, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    async def ensure_tracked(self, names: Sequence[str]) -> None:
        payload = [{"subreddit": name.lower(), "active": True} for name in names]
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/rest/v1/tracked_subs", headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                params={"on_conflict": "subreddit"}, json=payload, timeout=20,
            )
        response.raise_for_status()

    async def tracked_names(self) -> list[str]:
        rows = await self._get("tracked_subs", active="eq.true", select="subreddit")
        return [row["subreddit"] for row in rows]

    async def all_posts(self) -> Sequence[PostFacts]:
        posts: list[PostFacts] = []
        for name in await self.tracked_names():
            posts.extend(await self.posts(name))
        return posts

    async def posts(self, subreddit: str) -> Sequence[PostFacts]:
        rows = await self._get("sub_posts", subreddit=f"eq.{subreddit.lower()}")
        return [PostFacts(
            reddit_post_id=row["reddit_post_id"], subreddit=row["subreddit"],
            created_utc=datetime.fromisoformat(row["created_utc"].replace("Z", "+00:00")),
            status=row["status"], removed_by=row.get("removed_by"), has_link=row["has_link"], title_length=row["title_length"],
            first_seen_at=datetime.fromisoformat(row["first_seen_at"].replace("Z", "+00:00")) if row.get("first_seen_at") else None,
            rechecked_at=datetime.fromisoformat(row["rechecked_at"].replace("Z", "+00:00")) if row.get("rechecked_at") else None,
            link_domain=row.get("link_domain"), is_self_promo=row.get("is_self_promo"),
            flair=row.get("flair"), author_age_days=row.get("author_age_days"),
            author_karma=row.get("author_karma"), author_sub_comments=row.get("author_sub_comments"),
            author_posts_today=row.get("author_posts_today"),
        ) for row in rows]

    async def save_posts(self, posts: Sequence[PostFacts]) -> None:
        payload = [{
            **asdict(post), "created_utc": post.created_utc.isoformat(),
            "first_seen_at": post.first_seen_at.isoformat() if post.first_seen_at else None,
            "rechecked_at": post.rechecked_at.isoformat() if post.rechecked_at else None,
        } for post in posts]
        if not payload:
            return
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/rest/v1/sub_posts", headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                params={"on_conflict": "reddit_post_id"}, json=payload, timeout=30,
            )
        response.raise_for_status()

    async def sidebar_rules(self, subreddit: str) -> str:
        rows = await self._get("tracked_subs", subreddit=f"eq.{subreddit.lower()}", select="sidebar_rules")
        return str(rows[0].get("sidebar_rules") or "") if rows else ""

    async def save_rule(self, subreddit: str, evaluated: EvaluatedRule) -> None:
        payload = {
            "subreddit": subreddit.lower(), "rule_text": evaluated.candidate.rule_text,
            "condition": evaluated.candidate.condition, "correct": evaluated.correct,
            "tested": evaluated.tested, "status": "active",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/rest/v1/sub_rules", headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                params={"on_conflict": "subreddit,rule_text"}, json=[payload], timeout=20,
            )
        response.raise_for_status()

    async def active_rules(self, subreddit: str) -> Sequence[dict]:
        return await self._get("sub_rules", subreddit=f"eq.{subreddit.lower()}", status="eq.active",
                               select="id,rule_text,condition,correct,tested,learned_at")

    async def feedback_wrong(self, rule_id: str, user_id: str, week_start: str) -> int:
        async with httpx.AsyncClient() as client:
            write = await client.post(
                f"{self.url}/rest/v1/rule_feedback", headers={**self.headers, "Prefer": "resolution=ignore-duplicates"},
                params={"on_conflict": "rule_id,user_id,verdict,week_start"},
                json=[{"rule_id": rule_id, "user_id": user_id, "verdict": "wrong", "week_start": week_start}], timeout=20,
            )
            write.raise_for_status()
            votes = await client.get(
                f"{self.url}/rest/v1/rule_feedback", headers=self.headers,
                params={"rule_id": f"eq.{rule_id}", "verdict": "eq.wrong", "week_start": f"eq.{week_start}", "select": "id"}, timeout=20,
            )
            votes.raise_for_status()
            count = len(votes.json())
            if count >= 3:
                hidden = await client.patch(
                    f"{self.url}/rest/v1/sub_rules", headers=self.headers, params={"id": f"eq.{rule_id}"},
                    json={"status": "hidden", "hidden_at": "now()"}, timeout=20,
                )
                hidden.raise_for_status()
        return count


class MemoryStore:
    """Small deterministic store for tests and local demonstrations."""
    def __init__(self, posts: Sequence[PostFacts] = (), sidebar: str = ""):
        self._posts = list(posts)
        self._sidebar = sidebar
        self.tracked: list[str] = []
        self.rules: list[dict] = []
        self._votes: set[tuple[str, str, str]] = set()

    async def ensure_tracked(self, names: Sequence[str]) -> None:
        for name in names:
            key = name.lower()
            if key not in self.tracked:
                self.tracked.append(key)

    async def tracked_names(self) -> list[str]:
        return list(self.tracked)

    async def all_posts(self) -> Sequence[PostFacts]:
        return list(self._posts)

    async def posts(self, subreddit: str) -> Sequence[PostFacts]:
        return [p for p in self._posts if p.subreddit == subreddit.lower()]

    async def save_posts(self, posts: Sequence[PostFacts]) -> None:
        known = {p.reddit_post_id: p for p in self._posts}
        known.update({p.reddit_post_id: p for p in posts})
        self._posts = list(known.values())

    async def sidebar_rules(self, subreddit: str) -> str:
        return self._sidebar

    async def save_rule(self, subreddit: str, evaluated: EvaluatedRule) -> None:
        self.rules.append({
            "id": f"rule-{len(self.rules) + 1}", "subreddit": subreddit.lower(),
            "rule_text": evaluated.candidate.rule_text, "condition": evaluated.candidate.condition,
            "correct": evaluated.correct, "tested": evaluated.tested, "status": "active",
            "learned_at": "2026-10-25T00:00:00+00:00",
        })

    async def active_rules(self, subreddit: str) -> Sequence[dict]:
        return [r for r in self.rules if r["subreddit"] == subreddit.lower() and r["status"] == "active"]

    async def feedback_wrong(self, rule_id: str, user_id: str, week_start: str) -> int:
        self._votes.add((rule_id, user_id, week_start))
        count = sum(rule == rule_id and week == week_start for rule, _, week in self._votes)
        if count >= 3:
            for row in self.rules:
                if row["id"] == rule_id:
                    row["status"] = "hidden"
        return count
