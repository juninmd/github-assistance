"""Merge decision and execution for the PR Assistant.

Extracted from ``agent.py`` (Antigravity 150-line guideline). The merge is
gated by the non-bypassable ``MergePolicy`` and the per-repository autonomy.
"""

from __future__ import annotations

import time
from typing import Any

from src.agents.pr_assistant.merge_decision import evaluate_comments_with_llm
from src.agents.pr_assistant.mixins_base import PRAssistantBase
from src.agents.pr_assistant.pipeline import check_pipeline_status


class MergeFlowMixin(PRAssistantBase):
    """Evaluates human comments, then merges only on green, SHA-locked evidence."""

    def _resolve_mergeable(self, pr, repo_name: str) -> Any | None:
        if pr.mergeable is not None:
            return pr
        time.sleep(3)
        try:
            pr = self.github_client.get_repo(repo_name).get_pull(pr.number)
        except Exception as e:
            self.log(f"Failed to re-fetch PR #{pr.number}: {e}", "WARNING")
        return pr if pr.mergeable is not None else None

    def _try_merge(self, pr, results: dict, issue_comments: list | None = None) -> None:
        repo_name = pr.base.repo.full_name
        autonomy = self.autonomy.for_repository(repo_name)
        should_merge, reason = self._evaluate_comments_with_llm(pr, issue_comments)
        if not should_merge:
            # Rejection or evaluator unavailability blocks/wait — never close the PR.
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": reason,
                    "repository": repo_name,
                }
            )
            return

        if not autonomy.allows_merge():
            self._record_blocked(results, pr, repo_name, f"autonomy_mode:{autonomy.mode}")
            return

        if self.simulation_mode:
            self.log(f"[SIMULATION] would merge PR #{pr.number} in {repo_name}")
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": "simulation",
                    "repository": repo_name,
                }
            )
            return

        mergeable_state = getattr(pr, "mergeable_state", None)
        if mergeable_state in (None, "unknown"):
            # GitHub computes this lazily; wait for the next event instead of guessing.
            self._record_blocked(results, pr, repo_name, "mergeable_state_unknown")
            return
        new_sha = ""
        # update-branch 422s on an up-to-date branch, so only call it when GitHub says behind.
        if mergeable_state == "behind":
            updated, msg, new_sha = self.github_client.update_pr_branch(pr)
            if not updated:
                self._record_blocked(results, pr, repo_name, f"update_branch_failed: {msg}")
                return
        try:
            pr = self.github_client.get_repo(repo_name).get_pull(pr.number)
        except Exception as e:
            self._record_blocked(results, pr, repo_name, f"refresh_failed: {e}")
            return
        expected_sha = new_sha or pr.head.sha
        status = check_pipeline_status(pr)
        decision = self.merge_policy.evaluate(
            status=status,
            expected_sha=expected_sha,
            current_sha=pr.head.sha,
            autonomy=autonomy,
        )
        if decision.action != "merge":
            self._record_blocked(
                results, pr, repo_name, "|".join(decision.reasons), sha=expected_sha
            )
            return

        success, msg = self.github_client.merge_pr(pr, expected_sha=expected_sha)
        if success:
            results["merged"].append(
                {
                    "action": "merged",
                    "pr": pr.number,
                    "title": pr.title,
                    "repository": repo_name,
                    "sha": expected_sha,
                }
            )
            self._notify_merged(pr, issue_comments)
            self.telegram.send_pr_notification(pr)
        else:
            self._notify_merge_failed(pr, msg, issue_comments)
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": "merge_failed",
                    "error": msg,
                    "repository": repo_name,
                }
            )

    def _record_blocked(
        self, results: dict, pr, repo_name: str, reason: str, sha: str | None = None
    ) -> None:
        entry = {
            "pr": pr.number,
            "title": pr.title,
            "reason": reason,
            "repository": repo_name,
        }
        if sha:
            entry["sha"] = sha
        results.setdefault("blocked", []).append(entry)

    def _evaluate_comments_with_llm(
        self, pr, issue_comments: list | None = None
    ) -> tuple[bool, str]:
        """Evaluate human comments; never approve by default on evaluator failure."""
        try:
            comments = (
                issue_comments if issue_comments is not None else list(pr.get_issue_comments())
            )
        except Exception as e:
            return False, f"evaluator_unavailable: {e}"
        decision = evaluate_comments_with_llm(
            self.ai_client, comments, self._is_trusted_author
        )
        return decision.decision == "merge", decision.reason
