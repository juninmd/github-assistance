"""
Senior Developer Agent - Expert in security, architecture, and CI/CD.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from os import getenv
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
        self._repo_info_cache: dict[str, Any] = {}

    def run(self) -> dict[str, Any]:
        """Execute the Senior Developer workflow."""
        self.check_rate_limit()
        repositories = self.get_allowed_repositories()
        if not repositories:
            return {"status": "skipped", "reason": "empty_allowlist"}

        self._repo_info_cache.clear()
        results = self._process_repositories(repositories)
        results["burst_tasks"] = self.burst_mgr.run_burst(repositories)
        return results

    def get_repository_info(self, repository: str) -> Any | None:
        if repository not in self._repo_info_cache:
            self._repo_info_cache[repository] = super().get_repository_info(repository)
        return self._repo_info_cache[repository]

    def _process_repositories(self, repositories: list[str]) -> dict[str, Any]:
        """Analyze each repository and create tasks as needed."""
        results = {
            "feature_tasks": [], "security_tasks": [], "cicd_tasks": [],
            "tech_debt_tasks": [], "modernization_tasks": [], "performance_tasks": [],
            "failed": [], "timestamp": datetime.now().isoformat()
        }
        with ThreadPoolExecutor(max_workers=min(4, len(repositories))) as executor:
            futures = {executor.submit(self._process_single_repo, repo): repo for repo in repositories}
            for future in as_completed(futures):
                repo = futures[future]
                try:
                    repo_results = future.result()
                    for key in ["feature_tasks", "security_tasks", "cicd_tasks", "tech_debt_tasks", "modernization_tasks", "performance_tasks"]:
                        results[key].extend(repo_results.get(key, []))
                    results["failed"].extend(repo_results.get("failed", []))
                except Exception as e:
                    self.log(f"Failed to process {repo}: {e}", "ERROR")
                    results["failed"].append({"repository": repo, "error": str(e)})
        return results

    def _process_single_repo(self, repo: str) -> dict[str, Any]:
        """Analyze a single repository and return its results."""
        repo_results: dict[str, Any] = {
            "feature_tasks": [], "security_tasks": [], "cicd_tasks": [],
            "tech_debt_tasks": [], "modernization_tasks": [], "performance_tasks": [],
            "failed": [],
        }
        self.log(f"Analyzing repository: {repo}")
        try:
            self._analyze_and_task(repo, repo_results)
        except Exception as e:
            self.log(f"Failed to process {repo}: {e}", "ERROR")
            repo_results["failed"].append({"repository": repo, "error": str(e)})
        return repo_results

    def _analyze_and_task(self, repo: str, results: dict[str, Any]):
        """Runs all analyses and creates tasks for a single repository."""
        analyses = [
            (self.analyzer.analyze_security, self.task_creator.create_security_task, "security_tasks", "needs_attention"),
            (self.analyzer.analyze_cicd, self.task_creator.create_cicd_task, "cicd_tasks", "needs_improvement"),
            (self.analyzer.ai_powered_audit, self.task_creator.create_audit_remediation_task, "security_tasks", "needs_attention"),
            (self.analyzer.analyze_roadmap_features, self.task_creator.create_feature_implementation_task, "feature_tasks", "has_features"),
            (self.analyzer.analyze_tech_debt, self.task_creator.create_tech_debt_task, "tech_debt_tasks", "needs_attention"),
            (self.analyzer.analyze_modernization, self.task_creator.create_modernization_task, "modernization_tasks", "needs_modernization"),
            (self.analyzer.analyze_performance, self.task_creator.create_performance_task, "performance_tasks", "needs_optimization"),
        ]

        for analyze_fn, create_fn, res_key, flag in analyses:
            analysis = analyze_fn(repo)
            if analysis.get(flag):
                result = create_fn(repo, analysis)
                results[res_key].append({"repository": repo, "opencode": result})

