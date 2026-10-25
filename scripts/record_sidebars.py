"""Store the written sidebar rules for the first ten subreddits."""
from __future__ import annotations

import asyncio
import csv
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gohook_hidden_rules.cohort import FIRST_TEN
from gohook_hidden_rules.service import fetch_sidebar
from scripts.first_collection import docker, load_env

ROOT = Path(__file__).resolve().parents[1]


def save_sidebars(rows: list[tuple[str, str]]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    sql = (
        "create temporary table load_rules (subreddit text, sidebar_rules text);\n"
        "copy load_rules from stdin with (format csv, force_not_null (subreddit, sidebar_rules));\n"
    )
    docker(
        "exec", "-i", "arc-solver-gohook-data", "psql", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", "postgres",
        input_text=sql + buffer.getvalue() + "\\.\n"
        "update public.tracked_subs t set sidebar_rules = l.sidebar_rules "
        "from load_rules l where t.subreddit = l.subreddit;\n",
    )


async def main() -> None:
    load_env()
    if not os.getenv("FETCHLAYER_TOKEN"):
        raise SystemExit("FETCHLAYER_TOKEN is not set")
    rows = []
    for name in FIRST_TEN:
        text = await fetch_sidebar(name)
        rows.append((name, text))
        print(f"{name}: {text.count(chr(10)) + 1 if text else 0} lines")
    save_sidebars(rows)
    print(f"stored {len(rows)}")


if __name__ == "__main__":
    asyncio.run(main())
