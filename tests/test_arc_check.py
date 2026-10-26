from gohook_arc.check import line_for, quote_is_in_thread, record, score_claims, split_threads


def test_fewer_than_five_threads_skips_the_check():
    assert split_threads([{"id": "1"}, {"id": "2"}])["result"] == "skipped"


def test_threads_are_dealt_two_to_writing_and_one_held_back():
    threads = [{"id": str(i), "subreddit": "saas"} for i in range(6)]
    split = split_threads(threads)
    assert [thread["id"] for thread in split["write"]] == ["0", "1", "3", "4"]
    assert [thread["id"] for thread in split["hold"]] == ["2", "5"]


def test_a_different_subreddit_is_held_back_when_one_is_available():
    threads = [{"id": str(i), "subreddit": "saas"} for i in range(5)]
    threads.append({"id": "other", "subreddit": "startups"})
    hold = split_threads(threads)["hold"]
    assert any(thread["subreddit"] == "startups" for thread in hold)


def test_pass_needs_six_of_ten_and_at_most_one_disagreement():
    claims = [{"verdict": "agrees"}] * 6 + [{"verdict": "disagrees"}]
    assert score_claims(claims)["result"] == "pass"
    assert score_claims([{"verdict": "agrees"}] * 5 + [{"verdict": "disagrees"}] * 2)["result"] == "fail"


def test_all_unmentioned_is_unclear_and_says_nothing():
    score = score_claims([{"verdict": "not_mentioned"}])
    assert score["result"] == "unclear"
    assert line_for(score) is None


def test_day_one_record_saves_pass_fail_or_skipped():
    skipped = record([{"id": "1"}])
    assert skipped["result"] == "skipped" and skipped["line"] is None
    passed = record(
        [{"id": str(i), "subreddit": "saas"} for i in range(5)],
        [{"verdict": "agrees"}] * 4,
    )
    assert passed["result"] == "pass"
    assert passed["hold_ids"] == ["2"]


def test_a_signal_quote_must_come_from_the_thread():
    assert quote_is_in_thread("What should I use instead of HubSpot?", "instead of HubSpot")
    assert not quote_is_in_thread("What should I use instead of HubSpot?", "I hate the price")
