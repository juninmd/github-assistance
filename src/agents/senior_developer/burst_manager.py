"""
Burst Session Manager for Senior Developer Agent.
"""
import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.agents import utils as agent_utils
from src.agents.base_agent import BaseAgent
from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer
from src.agents.senior_developer.task_creator import SeniorDeveloperTaskCreator


class SeniorDeveloperBurstManager:
    """Handles end-of-day session bursts for the Senior Developer Agent."""

    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self._analyzer: SeniorDeveloperAnalyzer = cast(SeniorDeveloperAnalyzer, getattr(agent, "analyzer"))
        self._task_creator: SeniorDeveloperTaskCreator = cast(SeniorDeveloperTaskCreator, getattr(agent, "task_creator"))

    def run_burst(self, repositories: list[str]) -> list[dict[str, Any]]:
        """Run a configurable end-of-day burst to consume available Jules sessions."""
        max_actions = int(os.getenv("JULES_BURST_MAX_ACTIONS", "0"))
        trigger_hour = int(os.getenv("JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3", "18"))
        now_h = (datetime.now(UTC) - timedelta(hours=3)).hour

        if max_actions <= 0 or now_h < trigger_hour or not repositories:
            return []

        daily_limit = int(os.getenv("JULES_DAILY_SESSION_LIMIT", "100"))
        actions_to_run = min(max_actions, max(daily_limit - self._count_today_sessions(), 0))

        if actions_to_run <= 0:
            return []

        return [self._execute_burst_action(repositories, i) for i in range(actions_to_run)]

    def _count_today_sessions(self) -> int:
        return agent_utils.count_today_sessions_utc_minus_3(
            self.agent.jules_client, self.agent.log
        )

    def _is_same_day(self, session: dict, target_date: Any) -> bool:
        return agent_utils.is_same_day_utc_minus_3(session, target_date)

    def _execute_burst_action(self, repositories: list[str], idx: int) -> dict[str, Any]:
        repo = repositories[idx % len(repositories)]
        try:
            return self._create_burst_task(repo, idx)
        except Exception as e:
            return {"repository": repo, "action": idx + 1, "error": str(e)}

    def _create_burst_task(self, repository: str, idx: int) -> dict[str, Any]:
        analysis_methods = [
            (self._analyzer.analyze_security, self._task_creator.create_security_task, "needs_attention"),
            (self._analyzer.analyze_cicd, self._task_creator.create_cicd_task, "needs_improvement"),
            (self._analyzer.analyze_tech_debt, self._task_creator.create_tech_debt_task, "needs_attention"),
            (self._analyzer.analyze_modernization, self._task_creator.create_modernization_task, "needs_modernization"),
            (self._analyzer.analyze_performance, self._task_creator.create_performance_task, "needs_optimization"),
            (self._analyzer.analyze_roadmap_features, self._task_creator.create_feature_implementation_task, "has_features"),
        ]
        analyze_fn, create_fn, flag_key = analysis_methods[idx % len(analysis_methods)]
        analysis = analyze_fn(repository)
        if not analysis.get(flag_key):
            return {"repository": repository, "action": idx + 1, "skipped": True, "reason": "no_findings"}

        result = create_fn(repository, analysis)
        return {"repository": repository, "action": idx + 1, "opencode": result, "task_type": create_fn.__name__}
