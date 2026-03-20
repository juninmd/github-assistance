"""CI Health Agent - monitors failing CI runs and notifies Telegram."""
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.ci_health.utils import remediate_pipeline
from src.ai import get_ai_client


class CIHealthAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, name="ci_health", enforce_repository_allowlist=False, **kwargs)
        self.target_owner = kwargs.get("target_owner", "juninmd")
        self.ai_provider = kwargs.get("ai_provider") or os.getenv("AI_PROVIDER", "ollama")
        self.ai_model = kwargs.get("ai_model") or os.getenv("AI_MODEL", "qwen3:1.7b")
        self.ai_config = kwargs.get("ai_config") or {}

    def _get_ai_client(self):
        try:
            return get_ai_client(provider=self.ai_provider, model=self.ai_model, **self.ai_config)
        except Exception as exc:
            self.log(f"AI client unavailable: {exc}", "WARNING")
            return None

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def _allowed_repositories(self) -> list[str]:
        user = self.github_client.g.get_user(self.target_owner)
        return [repo.full_name for repo in user.get_repos()]

    def run(self) -> dict[str, Any]:
        self.check_rate_limit()
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        failing: list[dict[str, str]] = []
        failures_by_repo: dict[str, dict[str, Any]] = {}

        for repo_name in self._allowed_repositories():
            try:
                repo = self.github_client.get_repo(repo_name)
                runs = list(repo.get_workflow_runs(status="completed"))[:30]
                for run in runs:
                    if run.created_at < cutoff: break
                    if run.conclusion in {"failure", "timed_out", "action_required"}:
                        failure = {"repo": repo.full_name, "name": run.name or "workflow", "branch": run.head_branch or "unknown", "url": run.html_url, "conclusion": run.conclusion}
                        failing.append(failure)
                        failures_by_repo.setdefault(repo_name, {"repo": repo, "failures": []})["failures"].append(failure)
            except Exception as exc:
                self.log(f"Failed to inspect CI for {repo_name}: {exc}", "WARNING")

        fix_actions: list[dict[str, Any]] = []
        for repo_name, entry in failures_by_repo.items():
            repo = entry["repo"]
            if getattr(repo, "private", True) or not entry.get("failures"): continue
            try:
                action = remediate_pipeline(self, repo, entry["failures"])
                if action: fix_actions.append(action)
            except Exception as exc:
                self.log(f"Failed remediation for {repo_name}: {exc}", "WARNING")

        self._send_summary(failing, fix_actions)
        return {"agent": "ci-health", "owner": self.target_owner, "failures": failing, "fix_actions": fix_actions, "count": len(failing)}

    def _send_summary(self, failing: list, fix_actions: list):
        esc = self.telegram.escape
        text = ["🧪 *CI Health Agent*", f"👤 Owner: `{esc(self.target_owner)}`", f"❗ Falhas últimas 24h: *{len(failing)}*"]
        for item in failing[:15]:
            text.append(f"• [{esc(item['repo'])}]({item['url']}) \\ - {esc(item['name'])} \\({esc(item['conclusion'])}\\)")
        if fix_actions:
            text.append("\n🔧 *Ações de correção iniciadas*")
            for act in fix_actions[:10]:
                if act.get("session_id"):
                    text.append(f"• `{esc(act['repository'])}`: sessão Jules criada (ID `{esc(str(act['session_id']))}`)")
                elif act.get("issue_url"):
                    text.append(f"• `{esc(act['repository'])}`: issue criada ([link]({esc(act['issue_url'])}))")
        self.telegram.send_message("\n".join(text), parse_mode="MarkdownV2")
