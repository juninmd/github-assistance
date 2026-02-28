"""
Senior Developer Agent - Expert in security, architecture, and CI/CD.
"""
import time
from datetime import UTC, datetime, timedelta
from os import getenv
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer
from src.agents.senior_developer.task_creator import SeniorDeveloperTaskCreator
from src.ai_client import get_ai_client


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
        **kwargs
    ):
        super().__init__(*args, name="senior_developer", **kwargs)
        ai_config = ai_config or {}
        ai_config["model"] = ai_model
        self.ai_client = get_ai_client(ai_provider, **ai_config)
        self.analyzer = SeniorDeveloperAnalyzer(self)
        self.task_creator = SeniorDeveloperTaskCreator(self)

    def run(self) -> dict[str, Any]:
        """Execute the Senior Developer workflow."""
        repositories = self.get_allowed_repositories()
        if not repositories:
            return {"status": "skipped", "reason": "empty_allowlist"}

        results = self._process_repositories(repositories)
        results["burst_tasks"] = self.run_end_of_day_session_burst(repositories)
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
                
                # Sequential delay to avoid rate limits and provide clear progress
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
        if sec.get("needs_attention"):
            results["security_tasks"].append({"repository": repo, "session_id": self.task_creator.create_security_task(repo, sec).get("id")})
        # CI/CD
        cicd = self.analyzer.analyze_cicd(repo)
        if cicd.get("needs_improvement"):
            results["cicd_tasks"].append({"repository": repo, "session_id": self.task_creator.create_cicd_task(repo, cicd).get("id")})
        # Features
        feat = self.analyzer.analyze_roadmap_features(repo)
        if feat.get("has_features"):
            results["feature_tasks"].append({"repository": repo, "session_id": self.task_creator.create_feature_implementation_task(repo, feat).get("id")})
        # Tech Debt
        debt = self.analyzer.analyze_tech_debt(repo)
        if debt.get("needs_attention"):
            results["tech_debt_tasks"].append({"repository": repo, "session_id": self.task_creator.create_tech_debt_task(repo, debt).get("id")})
        # Modernization
        mod = self.analyzer.analyze_modernization(repo)
        if mod.get("needs_modernization"):
            results["modernization_tasks"].append({"repository": repo, "session_id": self.task_creator.create_modernization_task(repo, mod).get("id")})
        # Performance
        perf = self.analyzer.analyze_performance(repo)
        if perf.get("needs_optimization"):
            results["performance_tasks"].append({"repository": repo, "session_id": self.task_creator.create_performance_task(repo, perf).get("id")})

    def run_end_of_day_session_burst(self, repositories: list[str]) -> list[dict[str, Any]]:
        """Run a configurable end-of-day burst to consume available Jules sessions."""
        max_actions = int(getenv("JULES_BURST_MAX_ACTIONS", "0"))
        trigger_hour = int(getenv("JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3", "18"))
        now_h = (datetime.now(UTC) - timedelta(hours=3)).hour
        
        if max_actions <= 0 or now_h < trigger_hour or not repositories:
            return []

        daily_limit = int(getenv("JULES_DAILY_SESSION_LIMIT", "100"))
        actions_to_run = min(max_actions, max(daily_limit - self.count_today_sessions_utc_minus_3(), 0))
        
        if actions_to_run <= 0:
            return []

        return [self._execute_burst_action(repositories, i) for i in range(actions_to_run)]

    def _execute_burst_action(self, repositories: list[str], idx: int) -> dict[str, Any]:
        """Executes a single burst action."""
        repo = repositories[idx % len(repositories)]
        try:
            return self.create_burst_task(repo, idx)
        except Exception as e:
            return {"repository": repo, "action": idx + 1, "error": str(e)}

    def count_today_sessions_utc_minus_3(self) -> int:
        """Count how many Jules sessions were already created on the current UTC-3 day."""
        try:
            sessions = self.jules_client.list_sessions(page_size=200)
            now_date = (datetime.now(UTC) - timedelta(hours=3)).date()
            return sum(1 for s in sessions if self._is_same_day(s, now_date))
        except Exception as e:
            self.log(f"Failed to list session quota: {e}", "WARNING")
            return 0

    def _is_same_day(self, session: dict[str, Any], target_date: Any) -> bool:
        created_at = session.get("createTime") or session.get("createdAt")
        if not created_at: return False
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return (dt.astimezone(UTC) - timedelta(hours=3)).date() == target_date
        except: return False

    def create_burst_task(self, repository: str, idx: int) -> dict[str, Any]:
        """Create one extra task, rotating through available prompt templates."""
        methods = [
            self.create_security_task, self.create_cicd_task,
            self.create_feature_implementation_task, self.create_tech_debt_task,
            self.create_modernization_task, self.create_performance_task
        ]
        method = methods[idx % len(methods)]
        empty_analysis = {"issues": ["Hardening opportunities."], "improvements": ["CI reliability."], "features": [{"title": "High impact roadmap item", "number": "N/A"}], "details": "Codebase refactor."}
        session = method(repository, empty_analysis)
        return {"repository": repository, "action": idx + 1, "session_id": session.get("id"), "task_type": method.__name__}

    def extract_session_datetime(self, session: dict[str, Any]) -> datetime | None:
        """Extract datetime from session dictionary."""
        created_at = session.get("createTime") or session.get("createdAt")
        if not created_at:
            return None
        try:
            return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

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
    def analyze_security(self, repo: str):
        return self.analyzer.analyze_security(repo)

    def analyze_cicd(self, repo: str):
        return self.analyzer.analyze_cicd(repo)

    def analyze_roadmap_features(self, repo: str):
        return self.analyzer.analyze_roadmap_features(repo)

    def analyze_tech_debt(self, repo: str):
        return self.analyzer.analyze_tech_debt(repo)

    def analyze_modernization(self, repo: str):
        return self.analyzer.analyze_modernization(repo)

    def analyze_performance(self, repo: str):
        return self.analyzer.analyze_performance(repo)
