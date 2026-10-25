from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

PostStatus = Literal["stayed", "removed", "pending", "skip"]
RuleStatus = Literal["active", "retired", "hidden"]


@dataclass(frozen=True)
class PostFacts:
    reddit_post_id: str
    subreddit: str
    created_utc: datetime
    status: PostStatus
    has_link: bool
    title_length: int
    first_seen_at: datetime | None = None
    rechecked_at: datetime | None = None
    link_domain: str | None = None
    is_self_promo: bool | None = None
    flair: str | None = None
    author_age_days: int | None = None
    author_karma: int | None = None
    author_sub_comments: int | None = None
    author_posts_today: int | None = None

    def rule_facts(self) -> dict[str, Any]:
        row = asdict(self)
        return {key: row[key] for key in (
            "has_link", "link_domain", "is_self_promo", "title_length", "flair",
            "author_age_days", "author_karma", "author_sub_comments", "author_posts_today",
        )}


@dataclass(frozen=True)
class CandidateRule:
    rule_text: str
    condition: dict[str, Any]


@dataclass(frozen=True)
class EvaluatedRule:
    candidate: CandidateRule
    correct: int
    tested: int
    removed_matches: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.tested if self.tested else 0.0

    @property
    def eligible(self) -> bool:
        return self.tested >= 10 and self.removed_matches > 0 and self.accuracy >= 0.70
