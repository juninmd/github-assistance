"""
Conflict Resolver Agent - Auto-resolves merge conflicts in Pull Requests using AI.
"""
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.pr_assistant.conflict_resolver import resolve_conflicts_autonomously


class ConflictResolverAgent(BaseAgent):
    """Monitors and resolves merge conflicts in PRs across all repositories."""

    ALLOWED_AUTHORS = [
        "juninmd", "Copilot", "Jules da Google",
        "google-labs-jules", "google-labs-jules[bot]",
        "gemini-code-assist", "gemini-code-assist[bot]",
        "imgbot[bot]", "renovate[bot]", "dependabot[bot]",
    ]

    def __init__(self, *args, ai_provider: str = "ollama", ai_model: str = "qwen3:1.7b", **kwargs):
        super().__init__(*args, name="conflict_resolver", enforce_repository_allowlist=False, **kwargs)
        self.ai_provider = ai_provider
        self.ai_model = ai_model

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def run(self) -> dict[str, Any]:
        """Execute the conflict resolution workflow."""
        self.log("Starting Conflict Resolver workflow")
        self.check_rate_limit()

        results = {"resolved": [], "closed": [], "timestamp": datetime.now().isoformat()}

        query = f"is:pr is:open archived:false user:{self.target_owner}"
        issues = self.github_client.search_prs(query)

        for issue in issues:
            try:
                pr = self.github_client.get_pr_from_issue(issue)
                if pr.mergeable is False and self._is_trusted_author(pr.user.login):
                    self._process_conflict(pr, results)
            except Exception as e:
                self.log(f"Error processing PR #{issue.number}: {e}", "ERROR")
                self.telegram.send_message(
                    f"❌ <b>CONFLICT RESOLVER — ERRO PR</b>\n"
                    f"PR: <code>#{issue.number}</code>\n"
                    f"<pre>{self.telegram.escape_html(str(e)[:300])}</pre>",
                    parse_mode="HTML",
                )

        self._send_summary(results)
        return results

    def _is_trusted_author(self, author: str) -> bool:
        normalized = [a.lower().replace("[bot]", "") for a in self.ALLOWED_AUTHORS]
        return author.lower().replace("[bot]", "") in normalized

    def _process_conflict(self, pr, results: dict):
        self.log(f"PR #{pr.number} in {pr.base.repo.full_name} has conflicts — resolving...")
        success, msg = resolve_conflicts_autonomously(
            pr, ai_provider=self.ai_provider, ai_model=self.ai_model
        )

        repo_name = pr.base.repo.full_name
        if success:
            results["resolved"].append({"pr": pr.number, "repo": repo_name, "msg": msg})
            self._notify_resolved(pr, msg)
        else:
            results["closed"].append({"pr": pr.number, "repo": repo_name, "error": msg})
            self._close_unresolvable(pr, msg)

    def _notify_resolved(self, pr, msg: str):
        author = pr.user.login if pr.user else "contributor"
        body = f"✅ **Conflitos de Merge Resolvidos**\n\nOlá @{author}, resolvi os conflitos automaticamente.\n\n**Detalhes:** {msg}"
        self.github_client.comment_on_pr(pr, body)
        try:
            repo_name = pr.base.repo.full_name
            self.telegram.send_message(
                f"✅ <b>CONFLITO RESOLVIDO</b>\n──────────────────────\n"
                f"📦 <b>Repo:</b> <code>{self.telegram.escape_html(repo_name)}</code>\n"
                f"🔀 <b>PR:</b> <a href=\"{pr.html_url}\">#{pr.number}</a> — {self.telegram.escape_html(pr.title)}\n"
                f"ℹ️ {self.telegram.escape_html(msg)}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    def _close_unresolvable(self, pr, error: str):
        """Comment explaining why the PR is being closed, then close it."""
        author = pr.user.login if pr.user else "contributor"
        try:
            self.github_client.comment_on_pr(
                pr,
                f"❌ **Não foi possível resolver os conflitos de merge**\n\n"
                f"Olá @{author}, tentei resolver os conflitos automaticamente mas não tive sucesso.\n\n"
                f"**Motivo:** {error}\n\n"
                "Este PR será encerrado. Abra um novo PR após resolver os conflitos manualmente.",
            )
            pr.edit(state="closed")
            self.log(f"Closed unresolvable PR #{pr.number} in {pr.base.repo.full_name}")
        except Exception as e:
            self.log(f"Failed to close PR #{pr.number}: {e}", "WARNING")
        try:
            repo_name = pr.base.repo.full_name
            self.telegram.send_message(
                f"🚫 <b>PR ENCERRADO — CONFLITO NÃO RESOLVIDO</b>\n──────────────────────\n"
                f"📦 <b>Repo:</b> <code>{self.telegram.escape_html(repo_name)}</code>\n"
                f"🔀 <b>PR:</b> <a href=\"{pr.html_url}\">#{pr.number}</a> — {self.telegram.escape_html(pr.title)}\n"
                f"<pre>{self.telegram.escape_html(error[:300])}</pre>",
                parse_mode="HTML",
            )
        except Exception:
            pass

    def _send_summary(self, results: dict):
        resolved = results.get("resolved", [])
        closed = results.get("closed", [])
        if not resolved and not closed:
            return

        esc = self.telegram.escape_html
        lines = [
            "🔧 <b>CONFLICT RESOLVER</b>",
            "──────────────────────",
            f"✅ <b>Resolvidos:</b> <code>{len(resolved)}</code>",
            f"🚫 <b>Encerrados:</b> <code>{len(closed)}</code>",
        ]

        for item in resolved[:5]:
            url = f"https://github.com/{item['repo']}/pull/{item['pr']}"
            lines.append(f'  └ <a href="{url}">{esc(item["repo"])} #{item["pr"]}</a> — <i>{esc(item["msg"])}</i>')

        for item in closed[:5]:
            url = f"https://github.com/{item['repo']}/pull/{item['pr']}"
            lines.append(f'  └ <a href="{url}">{esc(item["repo"])} #{item["pr"]}</a> — <i>{esc(item["error"])}</i>')

        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
