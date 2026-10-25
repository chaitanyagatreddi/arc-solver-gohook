"""Mountable FastAPI router for BanAware, Scout, cron, and feedback."""
from __future__ import annotations

import hmac
import os
from datetime import date, timedelta
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from .cohort import FIRST_TEN
from .conditions import InvalidCondition
from .service import Store, collect_fetchlayer_posts, collect_public_posts, matching_warnings, pipeline_counts, run_collection


class DraftFacts(BaseModel):
    facts: dict[str, Any]


def _week_start(today: date | None = None) -> str:
    today = today or date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def cron_authorized(secret: str | None, authorization: str | None) -> bool:
    expected = f"Bearer {secret}" if secret else ""
    if not expected or not authorization or len(authorization) != len(expected):
        return False
    return hmac.compare_digest(authorization, expected)


def hidden_rules_router(store: Store, current_user: Callable[[], Awaitable[str]], fetch=None) -> APIRouter:
    """Create a router using GoHook's existing authenticated-user dependency."""
    router = APIRouter(prefix="/hidden-rules", tags=["hidden-rules"])

    @router.get("/subreddits/{subreddit}")
    async def active_rules(subreddit: str):
        return await store.active_rules(subreddit.lower())

    @router.post("/subreddits/{subreddit}/evaluate")
    async def evaluate_draft(subreddit: str, body: DraftFacts):
        try:
            # Validate the complete fact vocabulary early; unknown inputs are harmless,
            # but malformed condition values must never be accepted by downstream code.
            return {"warnings": await matching_warnings(store, subreddit, body.facts)}
        except InvalidCondition as exc:
            raise HTTPException(500, "Stored learned rule is invalid") from exc

    @router.post("/rules/{rule_id}/wrong")
    async def wrong(rule_id: str, user_id: str = Depends(current_user)):
        votes = await store.feedback_wrong(rule_id, user_id, _week_start())
        return {"rule_id": rule_id, "wrong_votes": votes, "hidden": votes >= 3}

    @router.post("/scout/check/{username}")
    async def scout_check(username: str, subreddit: str, body: DraftFacts):
        """Scout supplies existing BanAware account facts and gets matching learned rules."""
        return {
            "username": username.removeprefix("u/"),
            "subreddit": subreddit.lower(),
            "warnings": await matching_warnings(store, subreddit, body.facts),
        }

    @router.post("/cron/collect")
    async def collect(authorization: str | None = Header(default=None)):
        if not cron_authorized(os.getenv("CRON_SECRET"), authorization):
            raise HTTPException(status_code=401, detail="Not allowed.")
        await store.ensure_tracked(FIRST_TEN)
        default_fetch = collect_fetchlayer_posts if os.getenv("FETCHLAYER_TOKEN") else collect_public_posts
        return await run_collection(store, FIRST_TEN, fetch or default_fetch)

    @router.get("/health")
    async def health(authorization: str | None = Header(default=None)):
        if not cron_authorized(os.getenv("CRON_SECRET"), authorization):
            raise HTTPException(status_code=401, detail="Not allowed.")
        posts = await store.all_posts()
        return {"tracked": await store.tracked_names(), **pipeline_counts(posts)}

    return router
