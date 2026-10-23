"""Advisory PR reviews (LiteLLM + opencode) for the PR Assistant.

Extracted from ``agent.py`` (Antigravity 150-line guideline). Reviews are
advisory only: they post a comment/label and never gate a merge. The host agent
initialises the clients and the single opencode review slot in ``__init__``.
"""

from __future__ import annotations

from src.agents.pr_assistant import review_flags
from src.agents.pr_assistant.llm_reviewer import (
    build_llm_review_comment,
    has_existing_llm_review_comment,
    review_pr_with_litellm,
)
from src.agents.pr_assistant.mixins_base import PRAssistantBase
from src.agents.pr_assistant.opencode_reviewer import has_existing_opencode_review_comment
from src.agents.pr_assistant.review_authors import is_jules
from src.agents.pr_assistant.review_flow import run_review
from src.agents.pr_assistant.review_gate import apply_gate, gate_enabled
from src.agents.pr_assistant.review_verdict import LABEL_COLORS, build_review_comment


class ReviewMixin(PRAssistantBase):
    """LiteLLM and opencode advisory reviews for a PR."""

    def _run_llm_review(self, pr, issue_comments: list | None = None) -> None:
        if not self.llm_reviewer_client or has_existing_llm_review_comment(pr, issue_comments):
            return
        try:
            success, report = review_pr_with_litellm(pr, self.llm_reviewer_client)
            if not success:
                self.log(f"LiteLLM review skipped for PR #{pr.number}: {report}", "WARNING")
                return
            comment = build_llm_review_comment(report)
            if not comment:
                return
            if review_flags.review_dry_run():
                self.log(f"[DRY-RUN] LiteLLM review for PR #{pr.number}:\n{comment}")
                return
            self.github_client.comment_on_pr(pr, comment)
        except Exception as e:
            self.log(f"LiteLLM review error on PR #{pr.number}: {e}", "WARNING")

    def _run_opencode_review(self, pr, issue_comments: list | None = None) -> None:
        """Advisory review via opencode+skills. Never raises, never affects merge."""
        if not self.opencode_review_active or has_existing_opencode_review_comment(pr, issue_comments):
            return
        if not self._acquire_review_slot(pr):
            return
        try:
            verdict = run_review(pr, self.review_ai_client)
            if verdict is None:
                # Clone/opencode failure hits every PR alike; stop paying the cost this run.
                self.opencode_review_active = False
                self.log(
                    f"opencode review unavailable for PR #{pr.number}; disabled for this run",
                    "WARNING",
                )
                return
            author = pr.user.login if getattr(pr, "user", None) else ""
            jules = is_jules(author)
            comment = build_review_comment(
                verdict, head_sha=getattr(pr.head, "sha", ""), jules=jules
            )
            if review_flags.review_dry_run():
                self.log(f"[DRY-RUN] opencode review for PR #{pr.number}:\n{comment}")
                return
            if comment:
                self.github_client.comment_on_pr(pr, comment)
            self._apply_review_label(pr, verdict.label)
            self._apply_review_gate(pr, verdict, jules)
            fixed = " · correções enviadas" if verdict.fixed else ""
            min_sev = review_flags.gate_min_severity()
            gated = " · gate crítico" if verdict.blocks(min_sev) else ""
            self.log(f"Reviewed PR #{pr.number}: {verdict.verdict} ({verdict.label}){fixed}{gated}")
        except Exception as e:
            self.opencode_review_active = False
            self.log(f"opencode review error on PR #{pr.number}: {e}", "WARNING")
        finally:
            self._opencode_review_slot.release()

    def _acquire_review_slot(self, pr) -> bool:
        """Take the single opencode slot if this run's review budget still allows it."""
        if not self._opencode_review_slot.acquire(timeout=self._review_wait):
            self.log(
                f"review slot busy after {self._review_wait}s; skipping PR #{pr.number} "
                "(retried next run)",
                "WARNING",
            )
            return False
        with self._review_lock:
            if self._reviews_started >= self._review_budget:
                self._opencode_review_slot.release()
                self.log(
                    f"review budget {self._review_budget}/run reached; skipping PR #{pr.number}",
                    "WARNING",
                )
                return False
            self._reviews_started += 1
        return True

    def _review_gate_enabled(self, pr) -> bool:
        if not gate_enabled():
            return False
        repo = pr.base.repo.full_name
        return self.autonomy.for_repository(repo).allows_write()

    def _apply_review_gate(self, pr, verdict, jules: bool) -> None:
        # Blocking findings gate every author, Jules included; Jules then fixes its own PR.
        apply_gate(
            pr,
            self.github_client,
            verdict,
            self._review_gate_enabled(pr),
            self.log,
            min_severity=review_flags.gate_min_severity(),
        )

    def _apply_review_label(self, pr, label: str) -> None:
        """Best-effort review label; a label failure must never break the review."""
        try:
            repo = pr.base.repo
            existing = {lb.name.lower() for lb in repo.get_labels()}
            if label.lower() not in existing:
                repo.create_label(name=label, color=LABEL_COLORS.get(label, "ededed"))
            self.github_client.add_label_to_pr(pr, label)
        except Exception as e:
            self.log(f"Could not apply review label '{label}' on PR #{pr.number}: {e}", "WARNING")
