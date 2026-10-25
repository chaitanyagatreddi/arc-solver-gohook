from datetime import datetime, timedelta, timezone

import pytest

from fastapi.testclient import TestClient

from gohook_hidden_rules.api import hidden_rules_router
from gohook_hidden_rules.cohort import FIRST_TEN
from gohook_hidden_rules.conditions import InvalidCondition, matches, validate
from gohook_hidden_rules.learner import evaluate, parse_candidates, split_posts
from gohook_hidden_rules.models import CandidateRule, PostFacts
from gohook_hidden_rules.service import classify_removal, due_for_recheck, post_from_fetchlayer, posts_from_rss, sidebar_text, stage_observations
from gohook_hidden_rules.stores import MemoryStore


def post(n: int, *, removed: bool = False, linked: bool = True, seen=None) -> PostFacts:
    return PostFacts(
        reddit_post_id=str(n), subreddit="saas", created_utc=datetime(2026, 10, 1, tzinfo=timezone.utc),
        status="removed" if removed else "stayed", has_link=linked, title_length=30, first_seen_at=seen,
    )


def test_condition_language_rejects_unknown_field_and_handles_missing_data():
    with pytest.raises(InvalidCondition):
        validate({"field": "moderator_mood", "op": "eq", "value": "strict"})
    condition = {"all": [{"field": "has_link", "op": "eq", "value": True}, {"field": "author_karma", "op": "lt", "value": 100}]}
    assert not matches(condition, {"has_link": True, "author_karma": None})
    assert matches(condition, {"has_link": True, "author_karma": 3})


def test_rule_passes_only_held_out_accuracy_and_volume_gate():
    candidate = CandidateRule("Links are removed.", {"field": "has_link", "op": "eq", "value": True})
    held_out = [post(i, removed=i < 8) for i in range(10)]
    result = evaluate(candidate, held_out)
    assert (result.correct, result.tested, result.accuracy, result.eligible) == (8, 10, 0.8, True)
    assert not evaluate(candidate, held_out[:9]).eligible


def test_stable_split_never_includes_pending_posts():
    items = [post(i, removed=i % 2 == 0) for i in range(20)]
    items.append(PostFacts("pending", "saas", datetime.now(timezone.utc), "pending", False, 1))
    first = split_posts(items, "SaaS")
    assert first == split_posts(items, "SaaS")
    assert all(item.status != "pending" for group in first for item in group)


def test_first_observation_is_pending_then_rechecked_after_a_day():
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    observed = post(1, removed=True)
    first = stage_observations([], [observed], now)[0]
    assert first.status == "pending"
    assert not due_for_recheck(first, now + timedelta(hours=23))
    second = stage_observations([first], [observed], now + timedelta(hours=25))[0]
    assert second.status == "removed"
    assert second.rechecked_at == now + timedelta(hours=25)


def test_deleted_and_sitewide_removals_are_skipped():
    assert classify_removal({"selftext": "[deleted]"}) == ("skip", None)
    assert classify_removal({"selftext": "", "removed_by_category": "anti_evil_ops"}) == ("skip", "anti_evil_ops")
    assert classify_removal({"selftext": "[removed]", "removed_by_category": "moderator"}) == ("removed", "moderator")


@pytest.mark.asyncio
async def test_three_distinct_wrong_votes_hide_a_rule():
    store = MemoryStore()
    await store.save_rule("saas", evaluate(CandidateRule("A", {"field": "has_link", "op": "eq", "value": True}), [post(i, removed=True) for i in range(10)]))
    assert await store.feedback_wrong("rule-1", "a", "2026-10-19") == 1
    assert await store.feedback_wrong("rule-1", "b", "2026-10-19") == 2
    assert await store.feedback_wrong("rule-1", "c", "2026-10-19") == 3
    assert await store.active_rules("saas") == []


def test_sidebar_text_keeps_written_rules_in_order():
    text = sidebar_text({"rules": [
        {"number": 1, "title": "No spam", "descriptionText": "Do not pitch."},
        {"number": 2, "title": "Be kind", "descriptionText": ""},
    ]})
    assert text == "1. No spam\nDo not pitch.\n\n2. Be kind"


def test_rss_page_keeps_learner_columns_only():
    feed = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <id>t3_abc</id><updated>2026-10-25T15:00:00+00:00</updated><title>Hello</title>
      <author><name>/u/ada</name></author><link href="https://example.com/tool"/>
    </entry></feed>"""
    parsed = posts_from_rss("SaaS", feed)[0]
    assert (parsed.reddit_post_id, parsed.subreddit, parsed.title_length, parsed.has_link, parsed.link_domain) == ("abc", "saas", 5, True, "example.com")


def test_fetchlayer_page_maps_learner_columns():
    item = {
        "id": "abc", "author": "ada", "title": "Hello", "domain": "example.com",
        "createdAt": "2026-10-25T15:00:00.000Z", "flair": "Show", "removed": None, "removedByCategory": None,
    }
    parsed = post_from_fetchlayer("SaaS", item)
    assert parsed is not None
    assert (parsed.reddit_post_id, parsed.subreddit, parsed.has_link, parsed.link_domain, parsed.flair, parsed.title_length) == (
        "abc", "saas", True, "example.com", "Show", 5,
    )
    deleted = post_from_fetchlayer("saas", {**item, "removedByCategory": "deleted"})
    assert deleted is not None and deleted.status == "skip"


def test_deleted_posts_stay_skipped_on_first_collection():
    observed = PostFacts("deleted", "saas", datetime(2026, 10, 25, tzinfo=timezone.utc), "skip", False, 1, removed_by=None)
    staged = stage_observations([], [observed], datetime(2026, 10, 25, tzinfo=timezone.utc))[0]
    assert staged.status == "skip"


def test_first_ten_is_the_founder_cohort():
    assert len(FIRST_TEN) == 10
    assert FIRST_TEN[:4] == ("saas", "startups", "indiehackers", "sideproject")


@pytest.mark.asyncio
async def test_collection_job_is_protected_and_reports_counts(monkeypatch):
    from fastapi import FastAPI

    async def fetch(subreddit, limit):
        if subreddit == "zapier":
            raise TimeoutError("reddit")
        return [post(subreddit, linked=True)]

    store = MemoryStore()
    app = FastAPI()

    async def user():
        return "user-1"

    app.include_router(hidden_rules_router(store, user, fetch=fetch))
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    client = TestClient(app)
    denied = client.post("/hidden-rules/cron/collect")
    assert denied.status_code == 401
    accepted = client.post("/hidden-rules/cron/collect", headers={"Authorization": "Bearer test-secret"})
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["failed"] == 1
    assert body["collected"] == 9
    assert await store.tracked_names() == list(FIRST_TEN)
    health = client.get("/hidden-rules/health", headers={"Authorization": "Bearer test-secret"})
    assert health.json()["pending"] == 9


def test_invalid_model_candidates_are_dropped():
    candidates = parse_candidates('{"rules":[{"rule_text":"ok","condition":{"field":"has_link","op":"eq","value":true}},{"rule_text":"bad","condition":{"field":"unknown","op":"eq","value":true}}]}')
    assert [rule.rule_text for rule in candidates] == ["ok"]
