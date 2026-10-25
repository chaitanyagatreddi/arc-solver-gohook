"""Standalone local host. GoHook should mount `hidden_rules_router` into main.py instead."""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException

from .api import hidden_rules_router
from .stores import SupabaseStore


async def require_user(x_user_id: str | None = Header(default=None)) -> str:
    """Local-only identity seam. Production must pass GoHook's verified Supabase identity."""
    if not x_user_id:
        raise HTTPException(401, "X-User-Id is required")
    return x_user_id


def create_app() -> FastAPI:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    app = FastAPI(title="GoHook hidden rules")
    app.include_router(hidden_rules_router(SupabaseStore(url, key), require_user))
    return app


app = create_app()
