#!/bin/sh
# Apply the hidden-rule migration to a throwaway Postgres database and prove:
# the service role can insert and delete a row, and browser roles cannot read it.
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
name=arc-solver-gohook-postgres
docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" -e POSTGRES_PASSWORD=postgres -p 55432:5432 postgres:16 >/dev/null

cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

ready=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
test "$ready" -eq 1

docker exec -i "$name" psql -v ON_ERROR_STOP=1 -U postgres <<'SQL'
create role anon nologin;
create role authenticated nologin;
create role service_role bypassrls login password 'service';
SQL
docker exec -i "$name" psql -v ON_ERROR_STOP=1 -U postgres < "$root/supabase/migrations/0001_hidden_rules.sql"
docker exec -i "$name" psql -v ON_ERROR_STOP=1 -U postgres -c "grant usage on schema public to service_role, anon, authenticated;"
docker exec -e PGPASSWORD=service -i "$name" psql -v ON_ERROR_STOP=1 -U service_role -d postgres <<'SQL'
insert into public.tracked_subs (subreddit, sidebar_rules) values ('saas', 'no spam');
insert into public.sub_posts (subreddit, reddit_post_id, created_utc, title_length)
  values ('saas', 'smoke', now(), 12);
insert into public.sub_rules (subreddit, rule_text, condition)
  values ('saas', 'smoke rule', '{"field":"has_link","op":"eq","value":true}');
insert into public.rule_feedback (rule_id, user_id, verdict, week_start)
  select id, gen_random_uuid(), 'wrong', current_date from public.sub_rules where rule_text = 'smoke rule';

delete from public.rule_feedback
  where rule_id in (select id from public.sub_rules where rule_text = 'smoke rule');
delete from public.sub_rules where rule_text = 'smoke rule';
delete from public.sub_posts where reddit_post_id = 'smoke';
delete from public.tracked_subs where subreddit = 'saas';
SQL

docker exec -i "$name" psql -v ON_ERROR_STOP=1 -U postgres <<'SQL'
grant usage on schema public to anon;
set role anon;
SQL
if docker exec -i "$name" psql -U postgres -c "set role anon; select * from public.tracked_subs;" >/dev/null 2>&1; then
  echo "anon was able to read tracked_subs" >&2
  exit 1
fi
echo "storage migration verified"
