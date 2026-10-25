-- GoHook hidden subreddit rules. Apply after BanAware's existing migrations.
create table if not exists public.tracked_subs (
  id uuid primary key default gen_random_uuid(),
  subreddit text not null unique,
  sidebar_rules text not null default '',
  active boolean not null default true,
  last_collected_at timestamptz,
  last_learned_at timestamptz,
  created_at timestamptz not null default now(),
  constraint tracked_subs_normalized check (subreddit = lower(subreddit))
);

create table if not exists public.sub_posts (
  id uuid primary key default gen_random_uuid(),
  subreddit text not null references public.tracked_subs(subreddit) on update cascade,
  reddit_post_id text not null unique,
  created_utc timestamptz not null,
  first_seen_at timestamptz not null default now(),
  rechecked_at timestamptz,
  status text not null default 'pending'
    check (status in ('stayed', 'removed', 'pending', 'skip')),
  removed_by text,
  has_link boolean not null default false,
  link_domain text,
  is_self_promo boolean,
  title_length integer not null,
  flair text,
  author_age_days integer,
  author_karma integer,
  author_sub_comments integer,
  author_posts_today integer,
  split text check (split in ('learn', 'test')),
  raw jsonb not null default '{}'::jsonb
);

create index if not exists sub_posts_recheck_idx
  on public.sub_posts (status, first_seen_at) where status = 'pending';
create index if not exists sub_posts_subreddit_idx
  on public.sub_posts (subreddit, created_utc desc);

create table if not exists public.sub_rules (
  id uuid primary key default gen_random_uuid(),
  subreddit text not null references public.tracked_subs(subreddit) on update cascade,
  rule_text text not null,
  condition jsonb not null,
  correct integer not null default 0,
  tested integer not null default 0,
  status text not null default 'active'
    check (status in ('active', 'retired', 'hidden')),
  learned_at timestamptz not null default now(),
  wrong_votes integer not null default 0,
  hidden_at timestamptz,
  unique (subreddit, rule_text)
);

create index if not exists sub_rules_active_idx
  on public.sub_rules (subreddit, status) where status = 'active';

create table if not exists public.rule_feedback (
  id uuid primary key default gen_random_uuid(),
  rule_id uuid not null references public.sub_rules(id) on delete cascade,
  user_id uuid not null,
  verdict text not null check (verdict in ('wrong')),
  week_start date not null,
  created_at timestamptz not null default now()
);
create unique index if not exists rule_feedback_one_vote_per_week_idx
  on public.rule_feedback (rule_id, user_id, verdict, week_start);

alter table public.tracked_subs enable row level security;
alter table public.sub_posts enable row level security;
alter table public.sub_rules enable row level security;
alter table public.rule_feedback enable row level security;
revoke all on public.tracked_subs, public.sub_posts, public.sub_rules, public.rule_feedback from anon, authenticated;
