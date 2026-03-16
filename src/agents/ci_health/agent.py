"""CI Health Agent - monitors failing CI runs and notifies Telegram."""
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent
from src.ai_client import get_ai_client


class CIHealthAgent(BaseAgent):
    def __init__(
        self,
        *args,
        target_owner: str = "juninmd",
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="ci_health", enforce_repository_allowlist=False, **kwargs)
        self.target_owner = target_owner
        self.ai_provider = ai_provider or os.getenv("AI_PROVIDER", "ollama")
        self.ai_model = ai_model or os.getenv("AI_MODEL", "qwen3:1.7b")
        self.ai_config = ai_config or {}

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

    def _create_issue_for_pipeline(self, repo: Any, failures_text: str) -> dict[str, Any] | None:
        """Create a GitHub issue describing the CI failures (fallback behavior)."""
        ai_client = self._get_ai_client()
        if ai_client:
            prompt = (
                f"Repository: {repo.full_name}\n"
                f"CI pipeline failures found in the last 24h:\n{failures_text}\n\n"
                "Write a concise GitHub issue body that explains the problem and suggests concrete steps to fix the workflow."
            )
            try:
                body = ai_client.generate(prompt).strip()
            except Exception as exc:
                self.log(f"AI generation failed: {exc}", "WARNING")
                body = f"CI pipeline failures:\n{failures_text}"
        else:
            body = f"CI pipeline failures:\n{failures_text}"

        try:
            issue = repo.create_issue(
                title="CI pipeline failing - please fix",
                body=body,
            )
            return {"repository": repo.full_name, "issue_number": issue.number, "issue_url": issue.html_url}
        except Exception as exc:
            self.log(f"Failed to create issue in {repo.full_name}: {exc}", "WARNING")
            return None

    def _remediate_pipeline(self, repo: Any, failures: list[dict[str, str]]) -> dict[str, Any] | None:
        """Attempt to remediate a failing CI pipeline for a public repository."""
        if self.has_recent_jules_session(repo.full_name, task_keyword="ci health"):
            self.log(f"Skipping remediation for {repo.full_name}: recent Jules session exists")
            return None

        failures_text = "\n".join(
            [f"- {f['name']} ({f['conclusion']}): {f['url']}" for f in failures]
        )

        instructions = self.load_jules_instructions(
            variables={
                "repository": repo.full_name,
                "failures": failures_text,
            }
        )

        try:
            session = self.create_jules_session(
                repository=repo.full_name,
                instructions=instructions,
                title=f"Fix CI pipeline for {repo.full_name}",
                wait_for_completion=False,
            )
            return {
                "repository": repo.full_name,
                "session_id": session.get("id"),
                "session_name": session.get("name") or session.get("title"),
            }
        except Exception as exc:
            self.log(f"Could not create Jules session for {repo.full_name}: {exc}", "WARNING")
            return self._create_issue_for_pipeline(repo, failures_text)

    def run(self) -> dict[str, Any]:
        self.check_rate_limit()
        cutoff = datetime.now(UTC) - timedelta(hours=24)

        failing: list[dict[str, str]] = []
        failures_by_repo: dict[str, dict[str, Any]] = {}

        for repo_name in self._allowed_repositories():
            try:
                repo = self.github_client.get_repo(repo_name)
                runs = repo.get_workflow_runs(status="completed")
                count = 0
                for run in runs:
                    if count >= 30:
                        break
                    count += 1
                    if run.created_at < cutoff:
                        break
                    if run.conclusion in {"failure", "timed_out", "action_required"}:
                        failure = {
                            "repo": repo.full_name,
                            "name": run.name or "workflow",
                            "branch": run.head_branch or "unknown",
                            "url": run.html_url,
                            "conclusion": run.conclusion,
                        }
                        failing.append(failure)
                        failures_by_repo.setdefault(repo_name, {"repo": repo, "failures": []})["failures"].append(failure)
            except Exception as exc:
                self.log(f"Failed to inspect CI for {repo_name}: {exc}", "WARNING")

        fix_actions: list[dict[str, Any]] = []
        for repo_name, entry in failures_by_repo.items():
            repo = entry["repo"]
            if getattr(repo, "private", True):
                self.log(f"Skipping remediation for private repo {repo.full_name}")
                continue
            # The dictionary only gets populated if there's a failure, so entry["failures"] is never empty.
            try:
                action = self._remediate_pipeline(repo, entry["failures"])
                if action:
                    fix_actions.append(action)
            except Exception as exc:
                self.log(f"Failed remediation for {repo_name}: {exc}", "WARNING")

        esc = self.telegram.escape
        text = [
            "🧪 *CI Health Agent*",
            f"👤 Owner: `{esc(self.target_owner)}`",
            f"❗ Falhas últimas 24h: *{len(failing)}*",
        ]
        for item in failing[:15]:
            text.append(
                f"• [{esc(item['repo'])}]({item['url']}) \\ - {esc(item['name'])} \\({esc(item['conclusion'])}\\)"
            )

        if fix_actions:
            text.append("")
            text.append("🔧 *Ações de correção iniciadas*")
            for act in fix_actions[:10]:
                if act.get("session_id"):
                    session_id = str(act.get("session_id"))
                    text.append(f"• `{esc(act['repository'])}`: sessão Jules criada (ID `{esc(session_id)}`)")
                elif act.get("issue_url"):
                    text.append(f"• `{esc(act['repository'])}`: issue criada ([link]({esc(act['issue_url'])}))")
                else:
                    text.append(f"• `{esc(act['repository'])}`: ação iniciada")

        self.telegram.send_message("\n".join(text), parse_mode="MarkdownV2")
        return {
            "agent": "ci-health",
            "owner": self.target_owner,
            "failures": failing,
            "fix_actions": fix_actions,
            "count": len(failing),
        }
