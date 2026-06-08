"""
PR Assistant Agent - Auto-merges PRs and manages pipelines.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.pr_assistant.clawpatch_reviewer import (
    build_review_comment,
    has_existing_review_comment,
    review_pr_with_clawpatch,
)
from src.agents.pr_assistant.conflict_resolver import resolve_conflicts_autonomously
from src.agents.pr_assistant.notifications import (
    notify_conflicts,
    notify_merge_failed,
    notify_pipeline_pending,
)
from src.agents.pr_assistant.pipeline import (
    build_failure_comment,
    check_pipeline_status,
    get_pipeline_error_logs,
    has_existing_failure_comment,
)
from src.agents.pr_assistant.pipeline_fixer import (
    build_marker,
    fix_pipeline_autonomously,
    max_attempts,
    pipeline_fix_enabled,
    read_attempt_state,
)
from src.agents.pr_assistant.telegram_summary import build_and_send_summary
from src.agents.pr_assistant.utils import is_trusted_author
from src.ai import get_ai_client

ALLOWED_AUTHORS = [
    "juninmd",
    "Copilot",
    "Jules da Google",
    "google-labs-jules",
    "google-labs-jules[bot]",
    "gemini-code-assist",
    "gemini-code-assist[bot]",
    "imgbot[bot]",
    "renovate[bot]",
    "dependabot[bot]",
]

BOT_REVIEWS = ["Jules da Google", "google-labs-jules", "gemini-code-assist"]
UNRESOLVED_CLOSE_LABEL = "ga:closed-unresolved"
UNRESOLVED_CLOSE_DAYS = 7


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
        bypass_validations: bool = False,
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
            self.ai_client = get_ai_client(
                ai_provider, model=ai_model, **(kwargs.get("ai_config") or {})
            )

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
            "merged": [],
            "conflicts_resolved": [],
            "closed_unresolved": [],
            "pipeline_failures": [],
            "pipeline_fixes_attempted": [],
            "skipped": [],
            "timestamp": datetime.now().isoformat(),
        }
        prs = self._get_prs_to_process()
        prs_lock = __import__("threading").Lock()

        def _safe_process(pr):
            local_results = {
                "merged": [],
                "conflicts_resolved": [],
                "closed_unresolved": [],
                "pipeline_failures": [],
                "pipeline_fixes_attempted": [],
                "skipped": [],
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
                        "<pre>Verifique os logs para detalhes.</pre>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            with prs_lock:
                for key in (
                    "merged",
                    "conflicts_resolved",
                    "closed_unresolved",
                    "pipeline_failures",
                    "pipeline_fixes_attempted",
                    "skipped",
                ):
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
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": "pr_too_young",
                    "repository": repo_name,
                }
            )
            return

        labels = {lb.name for lb in pr.get_labels()}
        if "auto-merge-skip" in labels:
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": "auto-merge-skip",
                    "repository": repo_name,
                }
            )
            return

        author = pr.user.login if pr.user else "unknown"
        if not self._is_trusted_author(author):
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": "untrusted_author",
                    "repository": repo_name,
                }
            )
            return

        self._ensure_assigned(pr)
        self._try_accept_suggestions(pr)
        issue_comments = pr.get_issue_comments()
        pr = self._update_branch_before_merge(pr, results)
        if pr is None:
            return

        if pr.mergeable is None:
            # GitHub computes mergeability lazily — wait and re-fetch once
            time.sleep(3)
            try:
                pr = self.github_client.get_repo(repo_name).get_pull(pr.number)
            except Exception as e:
                self.log(f"Failed to re-fetch PR #{pr.number}: {e}", "WARNING")
            if pr.mergeable is None:
                results["skipped"].append(
                    {
                        "pr": pr.number,
                        "title": pr.title,
                        "reason": "mergeable_unknown",
                        "repository": repo_name,
                    }
                )
                return

        if pr.mergeable is False:
            self._handle_conflicts(pr, results, issue_comments)
            return

        status = check_pipeline_status(pr)
        is_success = status["state"] == "success"
        match status["state"]:
            case "failure" | "error":
                self._warn_pipeline_failure(pr, status, results, issue_comments)
                self._try_fix_pipeline(pr, status, results, issue_comments)
            case _ if not is_success:
                self._notify_pipeline_pending(pr, status["state"], issue_comments)

        is_broken = status["state"] in ("failure", "error")

        if is_broken or not is_success:
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": f"pipeline_{status['state']}",
                    "repository": repo_name,
                }
            )
            return

        self._run_clawpatch_review(pr, issue_comments)
        self._try_merge(pr, results, issue_comments)

    def _is_pr_old_enough(self, pr) -> bool:
        if not pr.created_at:
            return True
        age = datetime.now(UTC) - pr.created_at.replace(tzinfo=UTC)
        return age >= timedelta(minutes=self.min_pr_age_minutes)

    def _is_stale_unresolved(self, pr) -> bool:
        if not isinstance(pr.created_at, datetime):
            return False
        created_at = pr.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return datetime.now(UTC) - created_at >= timedelta(days=UNRESOLVED_CLOSE_DAYS)

    def _close_stale_unresolved(self, pr, reason: str, results: dict) -> bool:
        if not self._is_stale_unresolved(pr):
            return False
        repo_name = pr.base.repo.full_name
        body = (
            "<!-- github-assistance-stale-unresolved -->\n"
            "## Pull request encerrado automaticamente\n\n"
            f"Este PR está aberto há pelo menos {UNRESOLVED_CLOSE_DAYS} dias e a automação "
            "não conseguiu deixá-lo apto para merge.\n\n"
            f"**Motivo final:** {reason}\n\n"
            "Abra um novo PR após corrigir o problema ou reabra este PR quando ele estiver pronto.\n\n"
            "---\n"
            "🤖 **Origem Automatizada**\n"
            "- **Agente:** `pr_assistant`\n"
            "- **Modelo:** `policy-engine`\n"
            "- **Repositório de origem:** "
            "[github-assistance](https://github.com/juninmd/github-assistance)"
        )
        try:
            self.github_client.comment_on_pr(pr, body)
            self.github_client.add_label_to_pr(pr, UNRESOLVED_CLOSE_LABEL)
            success, error = self.github_client.close_pr(pr)
        except Exception as exc:
            success, error = False, str(exc)
        item = {
            "pr": pr.number,
            "title": pr.title,
            "repository": repo_name,
            "reason": reason,
        }
        if success:
            results.setdefault("closed_unresolved", []).append(item)
            self.log(f"Closed stale unresolved PR #{pr.number} in {repo_name}")
            return True
        item["error"] = error
        results["skipped"].append(item)
        self.log(f"Failed to close stale PR #{pr.number}: {error}", "WARNING")
        return False

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
                self.github_client.comment_on_pr(pr, f"⚠️ PR encerrado.\n\nMotivo: {reason}")
                pr.edit(state="closed")
            except Exception as e:
                self.log(f"Failed to close PR #{pr.number}: {e}", "WARNING")
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": f"llm_rejected: {reason}",
                    "repository": pr.base.repo.full_name,
                }
            )
            return

        success, msg = self.github_client.merge_pr(pr)
        if success:
            results["merged"].append(
                {
                    "action": "merged",
                    "pr": pr.number,
                    "title": pr.title,
                    "repository": pr.base.repo.full_name,
                }
            )
            self.telegram.send_pr_notification(pr)
        else:
            self._notify_merge_failed(pr, msg, issue_comments)
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": "merge_failed",
                    "error": msg,
                    "repository": pr.base.repo.full_name,
                }
            )

    def _run_clawpatch_review(self, pr, issue_comments: list | None = None) -> None:
        if has_existing_review_comment(pr, issue_comments):
            return
        try:
            success, report = review_pr_with_clawpatch(pr)
            if not success:
                self.log(f"clawpatch review skipped for PR #{pr.number}: {report}", "WARNING")
                return
            comment = build_review_comment(report)
            if comment:
                self.github_client.comment_on_pr(pr, comment)
        except Exception as e:
            self.log(f"clawpatch review error on PR #{pr.number}: {e}", "WARNING")

    def _evaluate_comments_with_llm(
        self, pr, issue_comments: list | None = None
    ) -> tuple[bool, str]:
        try:
            comments = (
                issue_comments if issue_comments is not None else list(pr.get_issue_comments())
            )
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
            has_reject = bool(re.search(r"\bREJECT\b", upper))
            # Default to merge unless explicitly told to reject
            return (not has_reject, response)
        except Exception:
            return True, "Evaluation failed"

    def _ensure_assigned(self, pr) -> None:
        try:
            assignees = {a.login for a in pr.assignees}
            if self.target_owner not in assignees:
                self.github_client.add_assignee_to_pr(pr, self.target_owner)
        except Exception as e:
            self.log(f"Failed to assign PR #{pr.number}: {e}", "WARNING")

    def _is_dependabot_pr(self, pr) -> bool:
        return (pr.user.login if pr.user else "") in ("dependabot[bot]", "dependabot")

    def _handle_conflicts(self, pr, results: dict, issue_comments: list | None = None) -> None:
        if self._is_dependabot_pr(pr):
            if self.github_client.pr_has_non_bot_commits(pr):
                try:
                    already = any(
                        c.body and "@dependabot recreate" in c.body
                        for c in (issue_comments or [])
                    )
                    if not already:
                        self.github_client.comment_on_pr(pr, "@dependabot recreate")
                        self.log(f"Commented @dependabot recreate on altered PR #{pr.number}")
                    reason = "dependabot_recreate_requested"
                except Exception as e:
                    self.log(f"Failed to comment @dependabot recreate on PR #{pr.number}: {e}", "WARNING")
                    reason = "dependabot_conflict_skipped"
            else:
                self.log(f"Skipping conflict on unaltered Dependabot PR #{pr.number} — Dependabot handles it")
                reason = "dependabot_conflict_skipped"
            results["skipped"].append({
                "pr": pr.number,
                "title": pr.title,
                "reason": reason,
                "repository": pr.base.repo.full_name,
            })
            return

        success, msg = resolve_conflicts_autonomously(pr)
        if success:
            results["conflicts_resolved"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "repository": pr.base.repo.full_name,
                    "msg": msg,
                }
            )
            self._notify_conflict_resolved(pr, msg)
            return

        results["skipped"].append(
            {
                "pr": pr.number,
                "title": pr.title,
                "reason": "has_conflicts",
                "error": msg,
                "repository": pr.base.repo.full_name,
            }
        )
        if self._close_stale_unresolved(pr, f"conflito não resolvido: {msg}", results):
            return
        self._notify_conflicts(pr, issue_comments)

    def _update_branch_before_merge(self, pr, results: dict):
        if self._is_dependabot_pr(pr):
            return pr
        success, msg = self.github_client.update_pr_branch(pr)
        if not success:
            self.log(f"Could not update branch for PR #{pr.number}: {msg}", "WARNING")
            results["skipped"].append(
                {
                    "pr": pr.number,
                    "title": pr.title,
                    "reason": "branch_update_failed",
                    "error": msg,
                    "repository": pr.base.repo.full_name,
                }
            )
            return None

        self.log(f"Updated branch for PR #{pr.number}: {msg}")
        if msg == "Branch already current":
            return pr
        try:
            refreshed_pr = self.github_client.get_repo(pr.base.repo.full_name).get_pull(pr.number)
            return refreshed_pr or pr
        except Exception as e:
            self.log(f"Failed to re-fetch PR #{pr.number} after branch update: {e}", "WARNING")
            return pr

    def _notify_conflict_resolved(self, pr, msg: str) -> None:
        from src.agents.pr_assistant.notifications import notify_conflict_resolved

        notify_conflict_resolved(self.github_client, self.telegram, pr, msg)

    def _notify_conflicts(self, pr, issue_comments: list | None = None) -> None:
        notify_conflicts(self.github_client, self.telegram, pr, issue_comments)

    def _notify_merge_failed(self, pr, error: str, issue_comments: list | None = None) -> None:
        notify_merge_failed(self.github_client, self.telegram, pr, error, issue_comments)

    def _notify_pipeline_pending(self, pr, state: str, issue_comments: list | None = None) -> None:
        notify_pipeline_pending(self.github_client, self.telegram, pr, state, issue_comments)

    def _warn_pipeline_failure(
        self, pr, status: dict, results: dict, issue_comments: list | None = None
    ) -> None:
        results["pipeline_failures"].append(
            {
                "action": "pipeline_failure",
                "pr": pr.number,
                "title": pr.title,
                "state": status["state"],
                "repository": pr.base.repo.full_name,
            }
        )
        if has_existing_failure_comment(pr, issue_comments):
            return
        comment = build_failure_comment(pr, status.get("failed_checks", []))
        try:
            self.github_client.comment_on_pr(pr, comment)
        except Exception as e:
            self.log(f"Failed to post pipeline-failure comment on PR #{pr.number}: {e}", "WARNING")

    def _try_fix_pipeline(
        self, pr, status: dict, results: dict, issue_comments: list | None = None
    ) -> None:
        if not pipeline_fix_enabled():
            return

        comments = (
            issue_comments
            if issue_comments is not None
            else self.github_client.get_issue_comments(pr)
        )
        last_attempt, _ = read_attempt_state(comments)
        mx = max_attempts()
        if last_attempt >= mx:
            self._close_stale_unresolved(
                pr, f"pipeline ainda falhando após {last_attempt} tentativas", results
            )
            return

        logs_data = get_pipeline_error_logs(pr)
        error_logs = logs_data.get("logs", "")
        failed_checks = logs_data.get("failed_checks", []) or [
            item.get("context", "check") for item in status.get("failed_checks", [])
        ]
        attempt = last_attempt + 1
        success, msg, pushed_sha = fix_pipeline_autonomously(
            pr, error_logs, failed_checks, attempt, mx
        )
        sha = pushed_sha or pr.head.sha
        self._comment_pipeline_fix_attempt(pr, msg, attempt, mx, sha, success)
        results.setdefault("pipeline_fixes_attempted", []).append(
            {
                "pr": pr.number,
                "title": pr.title,
                "repository": pr.base.repo.full_name,
                "success": success,
                "msg": msg,
                "sha": sha,
            }
        )
        if not success and (attempt >= mx or self._is_stale_unresolved(pr)):
            self._close_stale_unresolved(pr, f"pipeline não resolvido: {msg}", results)

    def _comment_pipeline_fix_attempt(
        self, pr, msg: str, attempt: int, mx: int, sha: str, success: bool
    ) -> None:
        outcome = "apliquei uma correcao automatica" if success else "nao consegui corrigir"
        body = (
            f"**Tentativa {attempt}/{mx} de corrigir o pipeline**\n\n"
            f"Ola @{pr.user.login if pr.user else 'contributor'}, {outcome} via OpenCode.\n\n"
            f"**Detalhes:** {msg}\n\n{build_marker(attempt, sha)}"
        )
        try:
            self.github_client.comment_on_pr(pr, body)
        except Exception as e:
            self.log(f"Failed to comment pipeline fix attempt on PR #{pr.number}: {e}", "WARNING")
