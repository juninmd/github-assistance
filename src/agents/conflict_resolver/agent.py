"""Conflict Resolver Agent - auto-resolves merge conflicts in pull requests."""

from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.conflict_resolver.notifications import (
    send_manual_notice,
    send_resolution_notice,
    send_summary_notice,
)
from src.agents.pr_assistant.conflict_resolver import resolve_conflicts_autonomously


class ConflictResolverAgent(BaseAgent):
    MANUAL_CONFLICT_LABEL = "needs-manual-conflict-resolution"
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

    def __init__(self, *args, ai_provider: str = "ollama", ai_model: str = "qwen3:1.7b", **kwargs):
        super().__init__(
            *args, name="conflict_resolver", enforce_repository_allowlist=False, **kwargs
        )
        self.ai_provider = ai_provider
        self.ai_model = ai_model

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def run(self) -> dict[str, Any]:
        self.log("Starting Conflict Resolver workflow")
        self.check_rate_limit()
        results = {"resolved": [], "manual": [], "timestamp": datetime.now().isoformat()}
        query = f"is:pr is:open archived:false user:{self.target_owner}"
        self.log(f"Searching PRs in your repositories with query: {query}")

        try:
            for issue in self.github_client.search_prs(query):
                self._handle_issue(issue, results)
        except Exception as e:
            self.log(f"Failed to search PRs: {e}", "ERROR")

        self._send_summary(results)
        return results

    def _handle_issue(self, issue, results: dict) -> None:
        try:
            pr = self.github_client.get_pr_from_issue(issue)
            repo_full_name = pr.base.repo.full_name
            author = pr.user.login
            if (
                not self.can_work_on_repository(repo_full_name)
                or not self._is_trusted_author(author)
                or pr.mergeable is not False
            ):
                return
            self.log(f"Evaluating PR #{pr.number} in {repo_full_name} by {author}")
            self._process_conflict(pr, results)
        except Exception as e:
            if "secondary rate limit" in str(e).lower():
                self.log("Secondary rate limit hit - waiting 30s...", "WARNING")
                import time

                time.sleep(30)
            self.log(f"Error processing PR #{issue.number}: {e}", "ERROR")

    def _is_trusted_author(self, author: str) -> bool:
        allowed_users = self.allowlist.list_users() or self.ALLOWED_AUTHORS
        normalized = [a.lower().replace("[bot]", "") for a in allowed_users]
        return author.lower().replace("[bot]", "") in normalized

    def _process_conflict(self, pr, results: dict) -> None:
        self.log(f"PR #{pr.number} in {pr.base.repo.full_name} has conflicts - resolving...")
        success, msg = resolve_conflicts_autonomously(
            pr, ai_provider=self.ai_provider, ai_model=self.ai_model
        )
        repo_name = pr.base.repo.full_name
        if success:
            results["resolved"].append({"pr": pr.number, "repo": repo_name, "msg": msg})
            self._notify_resolved(pr, msg)
            return
        results["manual"].append({"pr": pr.number, "repo": repo_name, "error": msg})
        self._mark_manual_resolution_needed(pr, msg)

    def _notify_resolved(self, pr, msg: str) -> None:
        author = pr.user.login if pr.user else "contributor"
        self.github_client.comment_on_pr(
            pr,
            f"**Conflitos de merge resolvidos**\n\n"
            f"Ola @{author}, resolvi os conflitos automaticamente.\n\n"
            f"**Detalhes:** {msg}",
        )
        send_resolution_notice(self.telegram, pr, msg)

    def _mark_manual_resolution_needed(self, pr, error: str) -> None:
        author = pr.user.login if pr.user else "contributor"
        try:
            self.github_client.comment_on_pr(
                pr,
                f"**Nao foi possivel resolver os conflitos de merge**\n\n"
                f"Ola @{author}, tentei resolver os conflitos automaticamente sem sucesso.\n\n"
                f"**Motivo:** {error}\n\n"
                "Mantive o PR aberto e marquei para resolucao manual.",
            )
        except Exception as e:
            self.log(f"Failed to comment on PR #{pr.number}: {e}", "WARNING")

        success, msg = self.github_client.add_label_to_pr(pr, self.MANUAL_CONFLICT_LABEL)
        if success:
            self.log(f"Marked PR #{pr.number} in {pr.base.repo.full_name} for manual resolution")
        else:
            self.log(f"Failed to label PR #{pr.number}: {msg}", "WARNING")
        send_manual_notice(self.telegram, pr, error)

    def _send_summary(self, results: dict) -> None:
        resolved = results.get("resolved", [])
        manual = results.get("manual", [])
        if resolved or manual:
            send_summary_notice(self.telegram, resolved, manual)
