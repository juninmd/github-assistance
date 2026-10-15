"""Top-level PR Assistant run loop and PR discovery.

Extracted from ``agent.py`` (Antigravity 150-line guideline): fetch the PRs to
process, fan out to per-PR processing, and aggregate the run results.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from src.agents.pr_assistant.mixins_base import PRAssistantBase
from src.agents.pr_assistant.pipeline import check_pipeline_status
from src.agents.pr_assistant.telegram_summary import build_and_send_summary
from src.agents.utils import assign_owner, request_review_owner


class RunFlowMixin(PRAssistantBase):
    """Runs the PR Assistant over every in-scope PR."""

    def run(self) -> dict[str, Any]:
        self.log("Starting PR Assistant workflow")
        results: dict[str, Any] = {
            "merged": [],
            "conflicts_resolved": [],
            "pipeline_failures": [],
            "skipped": [],
            "blocked": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        prs = self._get_prs_to_process()
        prs_lock = threading.Lock()

        def _safe_process(pr):
            local_results = {
                "merged": [],
                "conflicts_resolved": [],
                "pipeline_failures": [],
                "skipped": [],
                "blocked": [],
            }
            try:
                self._process_pr(pr, local_results)
            except Exception as e:
                self.log(f"Error processing PR #{pr.number}: {e}", "ERROR")
                local_results["skipped"].append(
                    {
                        "pr": pr.number,
                        "title": getattr(pr, "title", "Unknown Title"),
                        "reason": "error",
                        "error": str(e),
                    }
                )
                try:
                    repo_name = pr.base.repo.full_name if hasattr(pr, "base") else "unknown"
                    self.telegram.send_message(
                        f"❌ <b>PR ASSISTANT — ERRO</b>\n──────────────────────\n"
                        f"📦 <b>Repo:</b> <code>{self.telegram.escape_html(repo_name)}</code>  "
                        f"PR: <code>#{pr.number}</code>\n"
                        f"<pre>{self.telegram.escape_html(str(e)[:300])}</pre>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            with prs_lock:
                for key in ("merged", "conflicts_resolved", "pipeline_failures", "skipped", "blocked"):
                    results[key].extend(local_results[key])

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_safe_process, pr): pr.number for pr in prs}
            for _ in as_completed(futures):
                pass

        build_and_send_summary(results, self.telegram, self.target_owner)
        return results

    def _get_prs_to_process(self) -> list:
        if self.pr_ref:
            return self._get_pr_from_ref(self.pr_ref)
        query = f"is:open is:pr user:{self.target_owner}"
        prs = []
        for issue in self.github_client.search_prs(query):
            try:
                prs.append(self.github_client.get_pr_from_issue(issue))
            except Exception as e:
                self.log(f"Could not resolve PR from issue: {e}", "WARNING")
        return prs

    def _get_pr_from_ref(self, ref: str) -> list:
        try:
            repo_slug, number = ref.rsplit("#", 1)
            repo = self.github_client.get_repo(repo_slug)
            return [repo.get_pull(int(number))]
        except Exception as e:
            self.log(f"Could not resolve PR ref {ref}: {e}", "ERROR")
            return []

    def _process_pr(self, pr, results: dict) -> None:
        repo_name = pr.base.repo.full_name
        self.log(f"Processing PR #{pr.number} in {repo_name}")
        # Before any skip: Jules-opened PRs are never created by this app, so this is their only assignment point.
        assign_owner(pr, self.target_owner, self.log)
        request_review_owner(pr, self.target_owner, self.log)

        if self._skip_young_pr(pr, results, repo_name):
            return
        if self._skip_labeled_pr(pr, results, repo_name):
            return
        if self._skip_untrusted_pr(pr, results, repo_name):
            return

        # Tag repos with no CI regardless of conflicts/draft, so they are findable.
        status = check_pipeline_status(pr)
        if status.get("no_ci"):
            self._tag_no_ci(pr)

        self._try_accept_suggestions(pr)
        issue_comments = list(pr.get_issue_comments())
        resolved_pr = self._resolve_mergeable(pr, repo_name)
        if resolved_pr is None:
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": "mergeable_unknown",
                    "repository": repo_name,
                }
            )
            return
        pr = resolved_pr

        if pr.mergeable is False:
            self._handle_conflicts(pr, results, issue_comments)
            return

        pipeline_skipped = self._handle_pipeline_and_skip(
            pr, results, issue_comments, status=status
        )
        if not pipeline_skipped:
            self._try_merge(pr, results, issue_comments)

        # Advisory reviews run after merge or pipeline checks so findings are reported;
        # a merged PR no longer needs one.
        merged = any(m.get("pr") == pr.number for m in results.get("merged", []))
        if not self.simulation_mode and not merged:
            self._run_llm_review(pr, issue_comments)
            self._run_opencode_review(pr, issue_comments)
