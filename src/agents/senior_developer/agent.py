"""
Senior Developer Agent - Expert in security, architecture, and CI/CD.
"""
import time
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer
from src.agents.senior_developer.task_creator import SeniorDeveloperTaskCreator
from src.ai_client import get_ai_client
from src.agents.senior_developer import utils


class SeniorDeveloperAgent(BaseAgent):
    """Senior Developer Agent that coordinates repository analysis and task creation."""

    @property
    def persona(self) -> str:
        """Load persona from instructions.md"""
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        """Load mission from instructions.md"""
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str = "gemini",
        ai_model: str = "gemini-2.5-flash",
        ai_config: dict[str, Any] | None = None,
        target_owner: str = "juninmd",
        **kwargs
    ):
        super().__init__(*args, name="senior_developer", **kwargs)
        self.target_owner = target_owner
        ai_config = ai_config or {}
        ai_config["model"] = ai_model
        self.ai_client = get_ai_client(ai_provider, **ai_config)
        self.analyzer = SeniorDeveloperAnalyzer(self)
        self.task_creator = SeniorDeveloperTaskCreator(self)

    def run(self) -> dict[str, Any]:
        """Execute the Senior Developer workflow."""
        self.check_rate_limit()
        repositories = self.get_allowed_repositories()
        if not repositories:
            return {"status": "skipped", "reason": "empty_allowlist"}

        results = self._process_repositories(repositories)
        results["burst_tasks"] = utils.run_end_of_day_session_burst(
            repositories, self.jules_client, self.analyzer, self.task_creator, self.log
        )
        return results

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
        return results

    def _analyze_and_task(self, repo: str, results: dict[str, Any]):
        """Runs all analyses and creates tasks for a single repository."""
        # Security
        sec = self.analyzer.analyze_security(repo)
        if sec.get("needs_attention") and not self.has_recent_jules_session(repo, "security"):
            results["security_tasks"].append({"repository": repo, "session_id": self.task_creator.create_security_task(repo, sec).get("id")})
        # CI/CD
        cicd = self.analyzer.analyze_cicd(repo)
        if cicd.get("needs_improvement") and not self.has_recent_jules_session(repo, "cicd"):
            results["cicd_tasks"].append({"repository": repo, "session_id": self.task_creator.create_cicd_task(repo, cicd).get("id")})
        # Features
        feat = self.analyzer.analyze_roadmap_features(repo)
        if feat.get("has_features") and not self.has_recent_jules_session(repo, "feature"):
            results["feature_tasks"].append({"repository": repo, "session_id": self.task_creator.create_feature_implementation_task(repo, feat).get("id")})
        # Tech Debt
        debt = self.analyzer.analyze_tech_debt(repo)
        if debt.get("needs_attention") and not self.has_recent_jules_session(repo, "tech_debt"):
            results["tech_debt_tasks"].append({"repository": repo, "session_id": self.task_creator.create_tech_debt_task(repo, debt).get("id")})
        # Modernization
        mod = self.analyzer.analyze_modernization(repo)
        if mod.get("needs_modernization") and not self.has_recent_jules_session(repo, "modernization"):
            results["modernization_tasks"].append({"repository": repo, "session_id": self.task_creator.create_modernization_task(repo, mod).get("id")})
        # Performance
        perf = self.analyzer.analyze_performance(repo)
        if perf.get("needs_optimization") and not self.has_recent_jules_session(repo, "performance"):
            results["performance_tasks"].append({"repository": repo, "session_id": self.task_creator.create_performance_task(repo, perf).get("id")})

    # Proxies for backward compatibility and test support
    def create_security_task(self, repo: str, analysis: dict[str, Any]):
        return self.task_creator.create_security_task(repo, analysis)

    def create_cicd_task(self, repo: str, analysis: dict[str, Any]):
        return self.task_creator.create_cicd_task(repo, analysis)

    def create_feature_implementation_task(self, repo: str, analysis: dict[str, Any]):
        return self.task_creator.create_feature_implementation_task(repo, analysis)

    def create_tech_debt_task(self, repo: str, analysis: dict[str, Any]):
        return self.task_creator.create_tech_debt_task(repo, analysis)

    def create_modernization_task(self, repo: str, analysis: dict[str, Any]):
        return self.task_creator.create_modernization_task(repo, analysis)

    def create_performance_task(self, repo: str, analysis: dict[str, Any]):
        return self.task_creator.create_performance_task(repo, analysis)

    # Analyzer proxies for backward compatibility and test support
    def analyze_security(self, repo: str): return self.analyzer.analyze_security(repo)
    def analyze_cicd(self, repo: str): return self.analyzer.analyze_cicd(repo)
    def analyze_roadmap_features(self, repo: str): return self.analyzer.analyze_roadmap_features(repo)
    def analyze_tech_debt(self, repo: str): return self.analyzer.analyze_tech_debt(repo)
    def analyze_modernization(self, repo: str): return self.analyzer.analyze_modernization(repo)
    def analyze_performance(self, repo: str): return self.analyzer.analyze_performance(repo)
