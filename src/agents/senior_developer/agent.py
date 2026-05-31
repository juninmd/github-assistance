"""
Senior Developer Agent - Expert in feature development, security, architecture, and CI/CD.
"""

import time
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer
from src.agents.senior_developer.burst_manager import SeniorDeveloperBurstManager
from src.agents.senior_developer.task_creator import ANALYSIS_METHODS, SeniorDeveloperTaskCreator
from src.ai import get_ai_client


class SeniorDeveloperAgent(BaseAgent):
    """Senior Developer Agent that coordinates repository analysis and task creation."""

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str = "ollama",
        ai_model: str = "qwen3:1.7b",
        ai_config: dict[str, Any] | None = None,
        target_owner: str = "juninmd",
        **kwargs,
    ):
        super().__init__(
            *args, name="senior_developer", enforce_repository_allowlist=True, **kwargs
        )
        self.target_owner = target_owner
        ai_config = ai_config or {}
        ai_config["model"] = ai_model
        self.ai_client = get_ai_client(ai_provider, **ai_config)
        self.analyzer = SeniorDeveloperAnalyzer(self)
        self.task_creator = SeniorDeveloperTaskCreator(self)
        self.burst_mgr = SeniorDeveloperBurstManager(self)

    def run(self) -> dict[str, Any]:
        """Execute the Senior Developer workflow."""
        self.check_rate_limit()
        repositories = self.get_allowed_repositories()
        if not repositories:
            return {"status": "skipped", "reason": "empty_allowlist"}

        self.telegram.send_message(
            f"🔧 <b>SENIOR DEVELOPER</b>\n──────────────────────\n"
            f"🚀 Iniciando análise de <code>{len(repositories)}</code> repositório(s)...",
            parse_mode="HTML",
        )

        results = self._process_repositories(repositories)
        results["burst_tasks"] = self.burst_mgr.run_burst(repositories)
        self._send_summary(results)
        return results

    def _send_summary(self, results: dict[str, Any]) -> None:
        task_keys = [
            "feature_tasks",
            "security_tasks",
            "cicd_tasks",
            "tech_debt_tasks",
            "modernization_tasks",
            "performance_tasks",
        ]
        created_counts = {
            k: sum(
                1 for item in results.get(k, [])
                if isinstance(item, dict)
                and isinstance(item.get("opencode"), dict)
                and item.get("opencode", {}).get("status") == "success"
            )
            for k in task_keys
        }
        skipped_counts = {
            k: sum(
                1 for item in results.get(k, [])
                if isinstance(item, dict)
                and isinstance(item.get("opencode"), dict)
                and item.get("opencode", {}).get("status") == "skipped"
            )
            for k in task_keys
        }
        total_created = sum(created_counts.values())
        total_skipped = sum(skipped_counts.values())
        failed = len(results.get("failed", []))
        lines = [
            "🔧 <b>SENIOR DEVELOPER — RESUMO</b>",
            "──────────────────────",
            f"📋 <b>Total de PRs abertas:</b> <code>{total_created}</code>",
        ]
        if total_skipped:
            lines.append(f"⏭️ <b>Ignoradas (PR existente/cooldown):</b> <code>{total_skipped}</code>")
        lines.extend([
            f"🔒 Security: <code>{created_counts['security_tasks']}</code>  "
            f"⚙️ CI/CD: <code>{created_counts['cicd_tasks']}</code>  "
            f"🚀 Feature: <code>{created_counts['feature_tasks']}</code>",
            f"🧹 Tech Debt: <code>{created_counts['tech_debt_tasks']}</code>  "
            f"🆕 Modern.: <code>{created_counts['modernization_tasks']}</code>  "
            f"⚡ Perf.: <code>{created_counts['performance_tasks']}</code>",
        ])
        if failed:
            lines.append(f"❌ <b>Falhas:</b> <code>{failed}</code>")

        # Collect PR URLs from all tasks that ran opencode
        pr_urls: list[tuple[str, str]] = []
        for key in task_keys:
            for item in results.get(key, []):
                oc = item.get("opencode", {})
                if isinstance(oc, dict) and oc.get("pr_url"):
                    pr_urls.append((item.get("repository", "?"), oc["pr_url"]))

        if pr_urls:
            lines.append("──────────────────────")
            lines.append("🔗 <b>PRs abertas:</b>")
            for repo, url in pr_urls[:8]:
                lines.append(f'  └ <a href="{url}">{self.telegram.escape_html(repo)}</a>')

        self.telegram.send_message("\n".join(lines), parse_mode="HTML")

    def _process_repositories(self, repositories: list[str]) -> dict[str, Any]:
        """Analyze each repository and create tasks as needed."""
        results = {
            "feature_tasks": [],
            "security_tasks": [],
            "cicd_tasks": [],
            "tech_debt_tasks": [],
            "modernization_tasks": [],
            "performance_tasks": [],
            "failed": [],
            "timestamp": datetime.now().isoformat(),
        }
        for i, repo in enumerate(repositories):
            try:
                self.log(f"[{i + 1}/{len(repositories)}] Analyzing repository: {repo}")
                self._analyze_and_task(repo, results)
                if i < len(repositories) - 1:
                    time.sleep(1)
            except Exception as e:
                self.log(f"Failed to process {repo}: {e}", "ERROR")
                results["failed"].append({"repository": repo, "error": str(e)})
                self.telegram.send_message(
                    f"❌ <b>SENIOR DEVELOPER — ERRO</b>\n──────────────────────\n"
                    f"📦 <b>Repo:</b> <code>{repo}</code>\n"
                    f"<pre>{self.telegram.escape_html(str(e)[:300])}</pre>",
                    parse_mode="HTML",
                )
        return results

    def _analyze_and_task(self, repo: str, results: dict[str, Any]):
        """Runs all analyses and creates tasks for a single repository."""
        for analyze_name, create_name, res_key, flag in ANALYSIS_METHODS:
            analyze_fn = getattr(self.analyzer, analyze_name)
            create_fn = getattr(self.task_creator, create_name)
            analysis = analyze_fn(repo)
            if analysis.get(flag):
                result = create_fn(repo, analysis)
                results[res_key].append({"repository": repo, "opencode": result})
