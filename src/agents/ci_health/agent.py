"""CI Health Agent - monitors failing CI runs and notifies Telegram."""
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent


class CIHealthAgent(BaseAgent):
    def __init__(self, *args, target_owner: str = "juninmd", **kwargs):
        super().__init__(*args, name="ci_health", **kwargs)
        self.target_owner = target_owner

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def _escape(self, text: str) -> str:
        if not text:
            return ""
        for char in ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            text = text.replace(char, f"\\{char}")
        return text

    def _allowed_repositories(self) -> list[str]:
        repos = self.get_allowed_repositories()
        if repos:
            return repos

        user = self.github_client.g.get_user(self.target_owner)
        return [repo.full_name for repo in user.get_repos()]

    def run(self) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        failing: list[dict[str, str]] = []

        for repo_name in self._allowed_repositories():
            try:
                repo = self.github_client.get_repo(repo_name)
                runs = repo.get_workflow_runs(status="completed")
                for run in runs[:30]:
                    if run.created_at < cutoff:
                        break
                    if run.conclusion in {"failure", "timed_out", "cancelled", "action_required"}:
                        failing.append(
                            {
                                "repo": repo.full_name,
                                "name": run.name or "workflow",
                                "branch": run.head_branch or "unknown",
                                "url": run.html_url,
                                "conclusion": run.conclusion,
                            }
                        )
            except Exception as exc:
                self.log(f"Failed to inspect CI for {repo_name}: {exc}", "WARNING")

        text = [
            "🧪 *CI Health Agent*",
            f"👤 Owner: `{self._escape(self.target_owner)}`",
            f"❗ Falhas últimas 24h: *{len(failing)}*",
        ]
        for item in failing[:15]:
            text.append(
                f"• [{self._escape(item['repo'])}]({item['url']}) - {self._escape(item['name'])} ({self._escape(item['conclusion'])})"
            )

        self.github_client.send_telegram_msg("\n".join(text), parse_mode="MarkdownV2")
        return {"agent": "ci-health", "owner": self.target_owner, "failures": failing, "count": len(failing)}
