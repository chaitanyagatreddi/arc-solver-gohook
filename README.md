# GoHook hidden-rule learner

An isolated implementation of the “Learn Each Subreddit's Hidden Rules” PRD. It was designed from the supplied GoHook commit without changing that repository.

## What is implemented

- Supabase migration for `tracked_subs`, `sub_posts`, `sub_rules`, and `rule_feedback`.
- Public Reddit JSON collection (up to 300 posts), with a read-only integration seam for Composio.
- 24–48 hour observation gate: first sightings are `pending`; only a later observation is eligible for removal labeling.
- Deleted authors and sitewide removals are excluded.
- Deterministic 70/30 learn/test split.
- GPT-4o-mini candidate generation restricted to a validated JSON condition language.
- Deterministic held-out validation: active only at ≥70% removal accuracy across at least 10 matching test posts, including at least one removal.
- Matching-warning API, Scout payload API, and authenticated “This rule is wrong” feedback. Three distinct wrong votes in a calendar week hide the rule.

## Run tests

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Apply the schema

Apply `supabase/migrations/0001_hidden_rules.sql` after GoHook’s BanAware migrations.

## Mount in GoHook

The source GoHook app already has FastAPI, Supabase REST, authenticated user dependencies, and `BanAware` / Scout surfaces. Mount the router using its existing verified user dependency—do not use the local `X-User-Id` development header:

```python
from gohook_hidden_rules import SupabaseStore, hidden_rules_router

store = SupabaseStore(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
app.include_router(hidden_rules_router(store, banaware._require_user))
```

Use:

- `POST /hidden-rules/subreddits/{subreddit}/evaluate` with trusted draft/account facts to obtain warning cards.
- `POST /hidden-rules/scout/check/{username}?subreddit=saas` with the same facts for Scout.
- `POST /hidden-rules/rules/{rule_id}/wrong` from the warning card.

The production cron must invoke `collect_and_stage` for the chosen subreddits and invoke `learn_subreddit` weekly. Collection and learning are intentionally separate: the latter cannot run until pending posts have been observed again.

## Known integration decisions still required

The PRD explicitly leaves these decisions open, so this repository does not invent them:

1. The first 10 and eventual 50 tracked subreddits.
2. Whether Composio supplies every author fact and removal field needed; public JSON is the fallback.
3. The product definition of `is_self_promo`.
4. How GoHook will attribute a user's later posted URL to `post_removed_after_warning_*`.
5. The scheduler/hosting path and production PostHog event ownership.
