# One-day plan — five hidden-rule milestones

**Day-one outcome:** a quiet, observable collection pipeline for ten selected subreddits. It does not show learned-rule warnings.

**Paused after:** sidebar rules are stored for the ten subreddits. The 250 posts stay pending until 2026-10-26 17:47 UTC.

## Milestone 1 — Pick the cohort
**Complete in:** 15 minutes

- [x] Working first 10 chosen from the founder brief and stored in `cohort.py`.
- [ ] Seed those names into live `tracked_subs`.
- [x] Record each subreddit's current sidebar rules. `sideproject` and `mistralai` publish none.

**Done when:** 10 active `tracked_subs` rows exist.

## Milestone 2 — Create safe storage
**Complete in:** 30 minutes

- [x] Apply `supabase/migrations/0001_hidden_rules.sql` on a local database.
- [x] Confirm the service role can write and delete rows in all four tables.
- [x] Confirm the browser role cannot read `tracked_subs`.
- [ ] Apply the same migration to GoHook's Supabase.

**Done when:** the migration succeeds and a smoke-test row can be inserted and deleted.

## Milestone 3 — First collection
**Complete in:** 90 minutes

- [x] Read one FetchLayer page, 25 posts, for every tracked subreddit. Public JSON stayed blocked.
- [x] Store initial observations as `pending`.
- [x] Save post ID, timestamps, and title/link/flair facts. The raw source response is not stored.
- [x] Mark deleted authors and sitewide removals as `skip`. None of these 250 posts were in that state.

**Done when:** every target subreddit has stored posts and no duplicate `reddit_post_id`.

## Milestone 4 — Recheck automation
**Complete in:** 60 minutes to configure

- [x] Protected collection route exists: `POST /hidden-rules/cron/collect`.
- [ ] Deploy that route on a daily schedule.
- [ ] Re-observe only posts that have waited 24–48 hours.
- [ ] Set their outcome to `removed`, `stayed`, or `skip`; retain `removed_by` when Reddit supplies it.
- [ ] Retry transient Reddit/API failures without relabeling posts.

**Done when:** the cron route is protected and a dry run identifies the pending posts it will recheck.

> The first real recheck cannot finish today: the PRD requires waiting 24–48 hours after collection.

## Milestone 5 — Operational proof
**Complete in:** 45 minutes

- [x] `GET /hidden-rules/health` returns collection, pending, rechecked, removed, stayed, and skipped counts.
- [x] Log collection, pending, rechecked, removed, skipped, and failure counts per subreddit. Local query: `python scripts/pipeline_status.py`.
- [ ] Add an operational alert for a failed collection or recheck.
- [ ] Save a manual verification query or dashboard view.
- [x] Write the handoff: runbook, cron secret location, and the next review date. See `HANDOFF.md`.

**Done when:** one operator can see pipeline health without opening raw rows.

## Not in the one-day scope

GPT rule proposals, held-out validation, BanAware warnings, Scout output, wrong-feedback UI, user-facing PostHog events, and weekly relearning begin only after the first rechecks produce enough labeled data.
