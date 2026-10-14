"""opencode-based advisory PR review: enable flag and idempotency marker.

The review itself lives in ``review_flow``; this module only decides whether the
advisory review is enabled and whether a review comment already exists for the
PR (so a re-run does not post twice).
"""

from __future__ import annotations

import os

from github.PullRequest import PullRequest

from src.agents.pr_assistant.review_verdict import REVIEW_MARKER

OPENCODE_REVIEW_MARKER = REVIEW_MARKER


def opencode_review_enabled() -> bool:
    return os.getenv("OPENCODE_REVIEW_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def has_existing_opencode_review_comment(
    pr: PullRequest, issue_comments: list | None = None
) -> bool:
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        return any(OPENCODE_REVIEW_MARKER in (c.body or "") for c in comments)
    except Exception:
        return False
