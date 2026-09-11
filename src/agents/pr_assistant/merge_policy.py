"""Centralized, non-bypassable merge policy.

Safe-merge invariants: checks of the current SHA must be conclusively green,
required evidence must exist, no check may be failed/pending/cancelled/unknown,
and the head SHA validated before merge must still match at merge time. There is
no allowlist by check-name and no billing/phrasing bypass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config.autonomy_policy import RepoAutonomy

TRANSIENT_REASONS = ("checks_pending", "checks_unknown", "no_evidence", "ai_unavailable")


@dataclass(frozen=True)
class MergeDecision:
    action: str  # merge | wait | blocked
    reasons: list[str] = field(default_factory=list)

    def block(self, reason: str) -> bool:
        return self.action == "blocked" and reason in self.reasons


class MergePolicy:
    """Pure decision logic; does not talk to GitHub."""

    def evaluate(
        self,
        *,
        status: dict[str, Any],
        expected_sha: str | None,
        current_sha: str | None,
        autonomy: RepoAutonomy,
    ) -> MergeDecision:
        reasons: list[str] = []
        state = status.get("state")
        if status.get("failed_checks"):
            reasons.append("checks_failed")
        elif status.get("cancelled_checks"):
            reasons.append("checks_cancelled")
        elif state == "unknown":
            reasons.append("checks_unknown")
        elif state == "pending":
            if autonomy.require_evidence and not status.get("has_evidence"):
                reasons.append("no_evidence")
            else:
                reasons.append("checks_pending")
        elif state != "success":
            reasons.append("checks_failed")
        if autonomy.require_evidence and not status.get("has_evidence"):
            if "no_evidence" not in reasons:
                reasons.append("no_evidence")
        missing = self._missing_required(status, autonomy.required_checks)
        if missing:
            reasons.append(f"missing_checks:{','.join(sorted(missing))}")
        if expected_sha and current_sha and current_sha != expected_sha:
            reasons.append("sha_changed")
        if not autonomy.allows_merge():
            reasons.append(f"autonomy_mode:{autonomy.mode}")
        if not reasons:
            return MergeDecision("merge", reasons)
        transient = any(r in TRANSIENT_REASONS for r in reasons)
        return MergeDecision("wait" if transient else "blocked", reasons)

    @staticmethod
    def _missing_required(status: dict[str, Any], required: tuple[str, ...]) -> list[str]:
        if not required:
            return []
        seen = {c["context"] for c in status.get("success_checks", [])}
        return [name for name in required if name not in seen]


def autonomy_blocks_merge(autonomy: RepoAutonomy) -> str | None:
    """Return the reason string when the repo policy forbids autonomous merge."""
    if not autonomy.allows_merge():
        return f"autonomy_mode:{autonomy.mode}"
    return None
