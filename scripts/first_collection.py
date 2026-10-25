"""Collect one public page for each of the first ten subreddits into local Postgres.

Stores the learner columns only. First sightings stay pending, except deleted
authors and sitewide removals, which stay skipped.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import subprocess
import time
from pathlib import Path

from gohook_hidden_rules.cohort import FIRST_TEN
from gohook_hidden_rules.service import collect_fetchlayer_posts, stage_observations

ROOT = Path(__file__).resolve().parents[1]
NAME = "arc-solver-gohook-data"
PORT = "55433"


def docker(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], input=input_text, text=True, check=True, capture_output=True)


def psql(sql: str) -> str:
    return docker("exec", "-i", NAME, "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres", "-c", sql).stdout


def ensure_database() -> None:
    existing = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", NAME], text=True, capture_output=True)
    if existing.returncode != 0:
        docker("run", "-d", "--name", NAME, "-e", "POSTGRES_PASSWORD=postgres", "-p", f"{PORT}:5432",
               "-v", f"{NAME}:/var/lib/postgresql/data", "postgres:16")
    elif existing.stdout.strip() != "true":
        docker("start", NAME)
    for _ in range(30):
        if subprocess.run(["docker", "exec", NAME, "pg_isready", "-U", "postgres"], capture_output=True).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("local database did not start")
    psql("""
        do $$ begin create role anon nologin; exception when duplicate_object then null; end $$;
        do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$;
        do $$ begin create role service_role bypassrls login password 'service'; exception when duplicate_object then null; end $$;
    """)
    migration = (ROOT / "supabase/migrations/0001_hidden_rules.sql").read_text()
    docker("exec", "-i", NAME, "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres", input_text=migration)
    psql("grant usage on schema public to service_role, anon, authenticated;")
    values = ", ".join(f"('{name}')" for name in FIRST_TEN)
    psql(f"insert into public.tracked_subs (subreddit) values {values} on conflict (subreddit) do nothing;")


def copy_posts(posts) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for post in posts:
        writer.writerow([
            post.subreddit, post.reddit_post_id, post.created_utc.isoformat(),
            post.first_seen_at.isoformat() if post.first_seen_at else "",
            post.status, post.removed_by or "", "true" if post.has_link else "false",
            post.link_domain or "", post.title_length, post.flair or "",
        ])
    sql = (
        "create temporary table load_posts (\n"
        "  subreddit text, reddit_post_id text, created_utc timestamptz, first_seen_at timestamptz,\n"
        "  status text, removed_by text, has_link boolean, link_domain text, title_length integer, flair text\n"
        ");\n"
        "copy load_posts from stdin with (format csv, null '');\n"
    )
    docker("exec", "-i", NAME, "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres",
           input_text=sql + buffer.getvalue() + "\\.\ninsert into public.sub_posts "
           "(subreddit, reddit_post_id, created_utc, first_seen_at, status, removed_by, has_link, link_domain, title_length, flair) "
           "select subreddit, reddit_post_id, created_utc, first_seen_at, status, nullif(removed_by, ''), has_link, "
           "nullif(link_domain, ''), title_length, nullif(flair, '') from load_posts "
           "on conflict (reddit_post_id) do nothing;\n")


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        key, _, value = line.partition("=")
        if key and value and key not in os.environ:
            os.environ[key] = value


async def main() -> None:
    load_env()
    ensure_database()
    stored = []
    failures = []
    for name in FIRST_TEN:
        try:
            observed = await collect_fetchlayer_posts(name, limit=25)
            staged = stage_observations([], observed)
            copy_posts(staged)
            stored.extend(staged)
            print(f"{name}: {len(staged)}")
        except Exception as exc:
            failures.append({"subreddit": name, "error": type(exc).__name__})
            print(f"{name}: failed {type(exc).__name__}")
    summary = psql("""
        select subreddit || ' ' || status || ' ' || count(*)
        from public.sub_posts group by subreddit, status order by subreddit, status;
    """)
    duplicate_check = psql("select count(*) - count(distinct reddit_post_id) from public.sub_posts;")
    report = {
        "page_size": 25,
        "source": "fetchlayer-community-posts",
        "stored_this_run": len(stored),
        "failures": failures,
        "duplicate_ids": int(duplicate_check.strip().splitlines()[-2].strip()),
        "counts": summary,
    }
    (ROOT / "collection_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("stored_this_run", "failures", "duplicate_ids")}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
