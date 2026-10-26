"""ARC check for a GoHook answer.

Write from most of the threads. Hold the rest back. Keep the answer only when
those held-back threads still agree. Fewer than five threads skips the check.
"""
from __future__ import annotations

from typing import Sequence


def split_threads(threads: Sequence[dict]) -> dict:
    """Two for writing, one held back, repeating. Under five threads, do not split."""
    if len(threads) < 5:
        return {"result": "skipped", "write": list(threads), "hold": []}
    write, hold = [], []
    for index, thread in enumerate(threads):
        (hold if index % 3 == 2 else write).append(thread)
    return {"result": "split", "write": write, "hold": hold}


def score_claims(claims: Sequence[dict]) -> dict:
    """Pass when at least 6 of 10 decided claims agree, and at most one disagrees."""
    agrees = sum(claim.get("verdict") == "agrees" for claim in claims)
    disagrees = sum(claim.get("verdict") == "disagrees" for claim in claims)
    unmentioned = sum(claim.get("verdict") == "not_mentioned" for claim in claims)
    decided = agrees + disagrees
    if decided == 0:
        result = "unclear"
    elif agrees / decided >= 0.6 and disagrees <= 1:
        result = "pass"
    else:
        result = "fail"
    return {
        "result": result,
        "agrees": agrees,
        "disagrees": disagrees,
        "not_mentioned": unmentioned,
    }


def quote_is_in_thread(thread_text: str, quote: str) -> bool:
    """A social-signal reason counts only when the quote is really in the thread."""
    text = " ".join((thread_text or "").split()).lower()
    snippet = " ".join((quote or "").split()).lower()
    return bool(snippet) and snippet in text


def _ids(threads: Sequence[dict]) -> list[str]:
    return [str(thread.get("id") or "") for thread in threads]


def record(threads: Sequence[dict], claims: Sequence[dict] | None = None) -> dict:
    """The row day 1 saves. Nothing here is shown to a person."""
    split = split_threads(threads)
    saved = {
        "result": "skipped" if split["result"] == "skipped" else None,
        "write_ids": _ids(split["write"]),
        "hold_ids": _ids(split["hold"]),
        "agrees": 0,
        "disagrees": 0,
        "not_mentioned": 0,
        "line": None,
    }
    if split["result"] == "skipped":
        return saved
    score = score_claims(claims or [])
    saved.update(score)
    saved["line"] = line_for(score)
    return saved


def line_for(score: dict) -> str | None:
    """The one line a person can see. Unclear and skipped stay quiet."""
    if score["result"] == "pass":
        decided = score["agrees"] + score["disagrees"]
        return f"Checked: {score['agrees']} of {decided} claims hold up on threads this answer did not use."
    if score["result"] == "fail":
        return f"Held back: this answer did not hold up on fresh threads ({score['disagrees']} claims disagreed)."
    return None
