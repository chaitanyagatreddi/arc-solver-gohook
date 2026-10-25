# GoHook hidden-rule learner

Isolated implementation of the “Learn Each Subreddit's Hidden Rules” PRD. GoHook itself has not been changed. This repo is not yet collecting live posts.

## Done

- Schema written for `tracked_subs`, `sub_posts`, `sub_rules`, and `rule_feedback`.
- Collector written for public Reddit JSON, up to 300 posts per subreddit.
- First sightings stay `pending`. A later observation after 24–48 hours can be labeled `removed`, `stayed`, or `skip`.
- Deleted authors and sitewide removals (`reddit`, `anti_evil_ops`) are marked `skip`.
- Learner code written: a stable 70/30 split, a restricted JSON condition language, and a held-out gate of at least 70% accuracy on at least 10 matching test posts.
- Warning, Scout, and “this rule is wrong” API code written. Three distinct wrong votes in a week hide a rule.
- Tests are written in `tests/test_hidden_rules.py`.
- One-day plan is in `MILESTONE-1.md`.
- Working first ten subreddits are in `src/gohook_hidden_rules/cohort.py`.
- `POST /hidden-rules/cron/collect` seeds those ten and collects them. It requires `Authorization: Bearer $CRON_SECRET`.
- `GET /hidden-rules/health` returns tracked, pending, rechecked, removed, stayed, and skipped counts behind the same secret.
- Code is pushed to https://github.com/chaitanyagatreddi/arc-solver-gohook.

## Pending

- Replace the working first ten in `cohort.py` if these are not the subreddits to track.
- Apply the verified migration to GoHook’s Supabase. Local Postgres already accepted it.
- Run the first collection again once Reddit public JSON is reachable. The local database has the ten subreddits and zero posts; Reddit returned 403.
- Deploy the protected daily recheck cron. The first real labels still need the 24–48 hour wait.
- Add a failure alert and a handoff for the collection job. Health counts already exist behind the cron secret.
- Mount this service into GoHook.
- Show warnings in BanAware, return them from Scout, and record PostHog events.
- Turn on weekly relearning after the first labeled data exists.
- Define `is_self_promo` and how a later user post is tied to a warning.

## Working first 10 subreddits

Stored in code. Not yet inserted into a live database:

1. `saas`
2. `startups`
3. `indiehackers`
4. `sideproject`
5. `automation`
6. `nocode`
7. `zapier`
8. `claudeai`
9. `localllama`
10. `mistralai`

## Run the tests

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Apply the schema

Apply `supabase/migrations/0001_hidden_rules.sql` after GoHook’s BanAware migrations.

## Mount in GoHook

Use GoHook’s verified user dependency. Do not use the local `X-User-Id` header in production.

```python
from gohook_hidden_rules import SupabaseStore, hidden_rules_router

store = SupabaseStore(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
app.include_router(hidden_rules_router(store, banaware._require_user))
```

- `POST /hidden-rules/subreddits/{subreddit}/evaluate` checks a draft against active rules.
- `POST /hidden-rules/scout/check/{username}?subreddit=saas` returns the same warnings for Scout.
- `POST /hidden-rules/rules/{rule_id}/wrong` records “this rule is wrong”.

Collection and learning stay separate. Learning waits until posts have been observed again.
