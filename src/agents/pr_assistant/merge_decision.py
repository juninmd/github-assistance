"""Structured LLM evaluation of human PR comments before an autonomous merge.

Failure or unavailability of the evaluator never approves by default: it
returns ``wait`` so the PR is rescheduled, and an explicit LLM rejection
returns ``blocked`` without the caller closing the PR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_DECISION_RE = re.compile(r"\b(MERGE|REJECT)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CommentDecision:
    decision: str  # merge | wait | blocked
    reason: str


def parse_structured_response(text: str | None) -> tuple[str | None, str]:
    """Extract (decision, reason) from a structured LLM answer.

    Returns (None, error) when the answer does not contain exactly one valid
    decision keyword — such responses must never approve a merge.
    """
    if not isinstance(text, str) or not text.strip():
        return None, "invalid_response: empty"
    matches = _DECISION_RE.findall(text)
    if len(matches) != 1:
        return None, f"invalid_response: expected one MERGE/REJECT (got {len(matches)})"
    decision = matches[0].upper()
    reason = text.strip()
    return decision, reason


def evaluate_comments_with_llm(
    ai_client: Any | None,
    comments: list[Any],
    is_trusted_author,
) -> CommentDecision:
    """Decide whether human comments permit an autonomous merge."""
    human = []
    for comment in comments[-10:]:
        user = getattr(comment, "user", None)
        if not user or is_trusted_author(user.login):
            continue
        if comment.body:
            human.append(comment)
    if not human:
        return CommentDecision("merge", "no_human_review")
    if ai_client is None:
        return CommentDecision("wait", "evaluator_unavailable")
    text = "\n".join(f"@{c.user.login}: {c.body[:300]}" for c in human)
    try:
        response = ai_client.generate(
            f"Analyze PR comments:\n{text}\nReply with MERGE or REJECT. "
            "If REJECT, provide a short reason."
        )
    except Exception as e:
        return CommentDecision("wait", f"evaluator_unavailable: {e}")
    decision, reason = parse_structured_response(response)
    if decision is None:
        return CommentDecision("wait", reason)
    if decision == "REJECT":
        return CommentDecision("blocked", f"llm_rejected: {reason}")
    return CommentDecision("merge", reason)
