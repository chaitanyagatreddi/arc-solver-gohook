"""Print local pipeline counts. Does not relabel posts."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.first_collection import psql


def main() -> None:
    print(psql("""
        select subreddit,
               count(*) as collected,
               count(*) filter (where status = 'pending') as pending,
               count(*) filter (where rechecked_at is not null) as rechecked,
               count(*) filter (where status = 'removed') as removed,
               count(*) filter (where status = 'stayed') as stayed,
               count(*) filter (where status = 'skip') as skipped,
               count(*) filter (
                 where status = 'pending'
                   and now() - coalesce(first_seen_at, created_utc) >= interval '24 hours'
                   and now() - coalesce(first_seen_at, created_utc) <= interval '72 hours'
               ) as due_now
        from public.sub_posts
        group by subreddit
        order by subreddit;
    """))
    print(psql("""
        select min(first_seen_at) as first_seen,
               min(first_seen_at) + interval '24 hours' as earliest_recheck
        from public.sub_posts;
    """))


if __name__ == "__main__":
    main()
