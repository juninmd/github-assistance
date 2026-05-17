"""
Senior Developer Agent - Expert in security, architecture, and CI/CD.
"""
import time
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer
from src.agents.senior_developer.burst_manager import SeniorDeveloperBurstManager
from src.agents.senior_developer.task_creator import SeniorDeveloperTaskCreator
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
        **kwargs
    ):
        super().__init__(*args, name="senior_developer", enforce_repository_allowlist=True, **kwargs)
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
        task_counts = {
            "feature": len(results.get("feature_tasks", [])),
            "security": len(results.get("security_tasks", [])),
            "cicd": len(results.get("cicd_tasks", [])),
            "tech_debt": len(results.get("tech_debt_tasks", [])),
            "modernization": len(results.get("modernization_tasks", [])),
            "performance": len(results.get("performance_tasks", [])),
        }
        total = sum(task_counts.values())
        failed = len(results.get("failed", []))
        lines = [
            "🔧 <b>SENIOR DEVELOPER — RESUMO</b>",
            "──────────────────────",
            f"📋 <b>Total de tarefas criadas:</b> <code>{total}</code>",
            f"🔒 Security: <code>{task_counts['security']}</code>  "
            f"⚙️ CI/CD: <code>{task_counts['cicd']}</code>  "
            f"🚀 Feature: <code>{task_counts['feature']}</code>",
            f"🧹 Tech Debt: <code>{task_counts['tech_debt']}</code>  "
            f"🆕 Modern.: <code>{task_counts['modernization']}</code>  "
            f"⚡ Perf.: <code>{task_counts['performance']}</code>",
        ]
        if failed:
            lines.append(f"❌ <b>Falhas:</b> <code>{failed}</code>")
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")

    def _process_repositories(self, repositories: list[str]) -> dict[str, Any]:
        """Analyze each repository and create tasks as needed."""
        results = {
            "feature_tasks": [], "security_tasks": [], "cicd_tasks": [],
            "tech_debt_tasks": [], "modernization_tasks": [], "performance_tasks": [],
            "failed": [], "timestamp": datetime.now().isoformat()
        }
        for i, repo in enumerate(repositories):
            try:
                self.log(f"[{i+1}/{len(repositories)}] Analyzing repository: {repo}")
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
        mappings = [
            (self.analyzer.analyze_security, self.task_creator.create_security_task, "security", "security_tasks", "needs_attention"),
            (self.analyzer.analyze_cicd, self.task_creator.create_cicd_task, "cicd", "cicd_tasks", "needs_improvement"),
            (self.analyzer.ai_powered_audit, self.task_creator.create_audit_remediation_task, "audit", "security_tasks", "needs_attention"),
            (self.analyzer.analyze_roadmap_features, self.task_creator.create_feature_implementation_task, "feature", "feature_tasks", "has_features"),
            (self.analyzer.analyze_tech_debt, self.task_creator.create_tech_debt_task, "tech_debt", "tech_debt_tasks", "needs_attention"),
            (self.analyzer.analyze_modernization, self.task_creator.create_modernization_task, "modernization", "modernization_tasks", "needs_modernization"),
            (self.analyzer.analyze_performance, self.task_creator.create_performance_task, "performance", "performance_tasks", "needs_optimization"),
        ]

        for analyze_fn, create_fn, _keyword, res_key, flag in mappings:
            analysis = analyze_fn(repo)
            if analysis.get(flag):
                result = create_fn(repo, analysis)
                results[res_key].append({"repository": repo, "opencode": result})

