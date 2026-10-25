# Handoff — hidden rules, 25 Oct 2026

This repo learns unwritten subreddit rules for GoHook. It does not show warnings yet. GoHook itself was not changed.

## What is true now

- Ten subreddits: saas, startups, indiehackers, sideproject, automation, nocode, zapier, claudeai, localllama, mistralai.
- Local Postgres container `arc-solver-gohook-data` on port 55433 holds 250 posts, 25 per subreddit. Every post is `pending`. No duplicate post ids.
- Written sidebar rules are stored on those ten rows. sideproject and mistralai publish none.
- Public Reddit JSON returns 403 from this machine. Collection uses FetchLayer.
- Latest local commit on `main`: `41f7c67`. Not all local commits are pushed.

## Next review

Earliest recheck: **2026-10-26 17:47 UTC** (26 Oct, 11:17pm IST).

Run `python scripts/pipeline_status.py`. A post is due when `due_now` is greater than 0. Do not label posts before that time. The useful window is 24–48 hours after first sight. The code still accepts a late check up to 72 hours.

## Secrets, and where they live

- `FETCHLAYER_TOKEN` is in this repo's `.env`. That file is gitignored. Do not commit it.
- `CRON_SECRET` is not set in this repo. The routes `POST /hidden-rules/cron/collect` and `GET /hidden-rules/health` reject a request unless `Authorization: Bearer $CRON_SECRET` matches.
- GoHook Supabase has not received `supabase/migrations/0001_hidden_rules.sql`.

## What is not done

- Deploy the daily cron.
- Recheck the 250 posts and label them stayed, removed, or skip.
- Alert when a collection fails.
- Mount the router into GoHook, then BanAware, Scout, and PostHog.
- Learn rules. That waits until enough posts are labeled removed.

## Sign-up email, separate feature

The Resend verification hook is already committed on GoHook `staging` (`1054fdb`, ancestor of `origin/staging`). Turning it on is still a manual step: deploy the backend, add `SEND_EMAIL_HOOK_SECRET`, and enable the Supabase Send Email hook. If that fails, turn the hook off and Supabase sends its own email again.
