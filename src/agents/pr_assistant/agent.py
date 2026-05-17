"""
PR Assistant Agent - Auto-merges PRs and manages pipelines.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.pr_assistant.notifications import (
    notify_conflicts,
    notify_merge_failed,
    notify_pipeline_pending,
)
from src.agents.pr_assistant.pipeline import (
    build_failure_comment,
    check_pipeline_status,
    has_existing_failure_comment,
)
from src.agents.pr_assistant.telegram_summary import build_and_send_summary
from src.agents.pr_assistant.utils import is_trusted_author
from src.ai import get_ai_client

ALLOWED_AUTHORS = [
    "juninmd", "Copilot", "Jules da Google", "google-labs-jules",
    "google-labs-jules[bot]", "gemini-code-assist", "gemini-code-assist[bot]",
    "imgbot[bot]", "renovate[bot]", "dependabot[bot]",
]

BOT_REVIEWS = ["Jules da Google", "google-labs-jules", "gemini-code-assist"]


class PRAssistantAgent(BaseAgent):
    """Monitors and processes PRs across all repositories."""

    def __init__(
        self,
        *args,
        ai_provider: str = "ollama",
        ai_model: str = "qwen3:1.7b",
        target_owner: str = "juninmd",
        min_pr_age_minutes: int = 10,
        pr_ref: str | None = None,
        bypass_validations: bool = True,
        comment_ai_enabled: bool = True,
        **kwargs,
    ):
        super().__init__(*args, name="pr_assistant", enforce_repository_allowlist=False, **kwargs)
        self.target_owner = target_owner
        self.min_pr_age_minutes = min_pr_age_minutes
        self.pr_ref = pr_ref
        self.bypass_validations = bypass_validations
        self.comment_ai_enabled = comment_ai_enabled
        self.ai_client = None
        if self.comment_ai_enabled:
            self.ai_client = get_ai_client(ai_provider, model=ai_model, **(kwargs.get("ai_config") or {}))

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def uses_repository_allowlist(self) -> bool:
        return False

    def run(self) -> dict[str, Any]:
        self.log("Starting PR Assistant workflow")
        results: dict[str, Any] = {
            "merged": [], "conflicts_resolved": [], "pipeline_failures": [], "skipped": [],
            "timestamp": datetime.now().isoformat(),
        }
        prs = self._get_prs_to_process()
        prs_lock = __import__('threading').Lock()

        def _safe_process(pr):
            local_results = {"merged": [], "conflicts_resolved": [], "pipeline_failures": [], "skipped": []}
            try:
                self._process_pr(pr, local_results)
            except Exception as e:
                self.log(f"Error processing PR #{pr.number}: {e}", "ERROR")
                local_results["skipped"].append({
                    "pr": pr.number, "title": getattr(pr, "title", "Unknown Title"),
                    "reason": "error", "error": str(e),
                })
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
                for key in ("merged", "conflicts_resolved", "pipeline_failures", "skipped"):
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

        if not self._is_pr_old_enough(pr):
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "pr_too_young", "repository": repo_name,
            })
            return

        labels = {lb.name for lb in pr.get_labels()}
        if "auto-merge-skip" in labels:
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "auto-merge-skip", "repository": repo_name,
            })
            return

        author = pr.user.login if pr.user else "unknown"
        if not self._is_trusted_author(author):
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "untrusted_author", "repository": repo_name,
            })
            return

        self._try_accept_suggestions(pr)
        issue_comments = list(pr.get_issue_comments())

        if pr.mergeable is None:
            # GitHub computes mergeability lazily — wait and re-fetch once
            time.sleep(3)
            try:
                pr = self.github_client.get_repo(repo_name).get_pull(pr.number)
            except Exception as e:
                self.log(f"Failed to re-fetch PR #{pr.number}: {e}", "WARNING")
            if pr.mergeable is None:
                results["skipped"].append({
                    "pr": pr.number, "title": pr.title,
                    "reason": "mergeable_unknown", "repository": repo_name,
                })
                return

        if pr.mergeable is False:
            self._handle_conflicts(pr, results, issue_comments)
            return

        status = check_pipeline_status(pr)
        is_success = status["state"] == "success"
        match status["state"]:
            case "failure" | "error":
                self._warn_pipeline_failure(pr, status, results, issue_comments)
            case _ if not is_success:
                self._notify_pipeline_pending(pr, status["state"], issue_comments)

        if not is_success and not self.bypass_validations:
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": f"pipeline_{status['state']}", "repository": repo_name,
            })
            return

        self._try_merge(pr, results, issue_comments)

    def _is_pr_old_enough(self, pr) -> bool:
        if not pr.created_at:
            return True
        age = datetime.now(UTC) - pr.created_at.replace(tzinfo=UTC)
        return age >= timedelta(minutes=self.min_pr_age_minutes)

    def _is_trusted_author(self, login: str) -> bool:
        return is_trusted_author(login, ALLOWED_AUTHORS)

    def _try_accept_suggestions(self, pr) -> None:
        try:
            _success, _msg, count = self.github_client.accept_review_suggestions(pr, BOT_REVIEWS)
            if count > 0:
                self.log(f"Applied {count} suggestions on PR #{pr.number}")
        except Exception as e:
            self.log(f"Error applying suggestions on PR #{pr.number}: {e}", "WARNING")

    def _try_merge(self, pr, results: dict, issue_comments: list | None = None) -> None:
        should_merge, reason = self._evaluate_comments_with_llm(pr, issue_comments)
        if not should_merge:
            try:
                self.github_client.comment_on_pr(pr, f"\u26a0\ufe0f PR encerrado.\n\nMotivo: {reason}")
                pr.edit(state="closed")
            except Exception as e:
                self.log(f"Failed to close PR #{pr.number}: {e}", "WARNING")
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": f"llm_rejected: {reason}", "repository": pr.base.repo.full_name,
            })
            return

        success, msg = self.github_client.merge_pr(pr)
        if success:
            results["merged"].append({
                "action": "merged", "pr": pr.number, "title": pr.title,
                "repository": pr.base.repo.full_name,
            })
            self.telegram.send_pr_notification(pr)
        else:
            self._notify_merge_failed(pr, msg, issue_comments)
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "merge_failed", "error": msg,
                "repository": pr.base.repo.full_name,
            })

    def _evaluate_comments_with_llm(self, pr, issue_comments: list | None = None) -> tuple[bool, str]:
        try:
            comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
            human = []
            for c in comments[-10:]:
                if not c.user or self._is_trusted_author(c.user.login):
                    continue
                if c.body and "You have reached your Codex usage limits" in c.body:
                    continue
                human.append(c)
            if not human:
                return True, "No human review"
            if self.ai_client is None:
                return True, "Comment AI disabled"
            text = "\n".join(f"@{c.user.login}: {c.body[:300]}" for c in human)
            response = self.ai_client.generate(
                f"Analyze PR comments:\n{text}\nReply with MERGE or REJECT. If REJECT, provide a short reason."
            )
            if not response:
                return True, "Empty response"
            upper = response.upper()
            has_reject = bool(re.search(r'\bREJECT\b', upper))
            # Default to merge unless explicitly told to reject
            return (not has_reject, response)
        except Exception:
            return True, "Evaluation failed"

    def _handle_conflicts(self, pr, results: dict, issue_comments: list | None = None) -> None:
        results["skipped"].append({
            "pr": pr.number, "title": pr.title,
            "reason": "has_conflicts", "repository": pr.base.repo.full_name,
        })
        self._notify_conflicts(pr, issue_comments)

    def _notify_conflict_resolved(self, pr, msg: str) -> None:
        from src.agents.pr_assistant.notifications import notify_conflict_resolved
        notify_conflict_resolved(self.github_client, self.telegram, pr, msg)

    def _notify_conflicts(self, pr, issue_comments: list | None = None) -> None:
        notify_conflicts(self.github_client, self.telegram, pr, issue_comments)

    def _notify_merge_failed(self, pr, error: str, issue_comments: list | None = None) -> None:
        notify_merge_failed(self.github_client, self.telegram, pr, error, issue_comments)

    def _notify_pipeline_pending(self, pr, state: str, issue_comments: list | None = None) -> None:
        notify_pipeline_pending(self.github_client, self.telegram, pr, state, issue_comments)

    def _warn_pipeline_failure(self, pr, status: dict, results: dict, issue_comments: list | None = None) -> None:
        results["pipeline_failures"].append({
            "action": "pipeline_failure", "pr": pr.number, "title": pr.title,
            "state": status["state"], "repository": pr.base.repo.full_name,
        })
        if has_existing_failure_comment(pr, issue_comments):
            return
        comment = build_failure_comment(pr, status.get("failed_checks", []))
        try:
            self.github_client.comment_on_pr(pr, comment)
        except Exception as e:
            self.log(f"Failed to post pipeline-failure comment on PR #{pr.number}: {e}", "WARNING")
