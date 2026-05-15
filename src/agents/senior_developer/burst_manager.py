"""
Burst Session Manager for Senior Developer Agent.
"""
import os
from datetime import UTC, datetime, timedelta
from typing import Any

class SeniorDeveloperBurstManager:
    """Handles end-of-day session bursts for the Senior Developer Agent."""

    def __init__(self, agent: Any):
        self.agent = agent

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
        """Count how many Jules sessions were already created on the current UTC-3 day."""
        try:
            sessions = self.agent.jules_client.list_sessions(page_size=200)
            now_date = (datetime.now(UTC) - timedelta(hours=3)).date()
            return sum(1 for s in sessions if self._is_same_day(s, now_date))
        except Exception as e:
            self.agent.log(f"Failed to list session quota: {e}", "WARNING")
            return 0

    def _is_same_day(self, session: dict[str, Any], target_date: Any) -> bool:
        created_at = session.get("createTime") or session.get("createdAt")
        if not created_at:
            return False
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return (dt.astimezone(UTC) - timedelta(hours=3)).date() == target_date
        except Exception:
            return False

    def _execute_burst_action(self, repositories: list[str], idx: int) -> dict[str, Any]:
        repo = repositories[idx % len(repositories)]
        try:
            return self._create_burst_task(repo, idx)
        except Exception as e:
            return {"repository": repo, "action": idx + 1, "error": str(e)}

    def _create_burst_task(self, repository: str, idx: int) -> dict[str, Any]:
        analysis_methods = [
            (self.agent.analyzer.analyze_security, self.agent.task_creator.create_security_task, "needs_attention"),
            (self.agent.analyzer.analyze_cicd, self.agent.task_creator.create_cicd_task, "needs_improvement"),
            (self.agent.analyzer.analyze_tech_debt, self.agent.task_creator.create_tech_debt_task, "needs_attention"),
            (self.agent.analyzer.analyze_modernization, self.agent.task_creator.create_modernization_task, "needs_modernization"),
            (self.agent.analyzer.analyze_performance, self.agent.task_creator.create_performance_task, "needs_optimization"),
            (self.agent.analyzer.analyze_roadmap_features, self.agent.task_creator.create_feature_implementation_task, "has_features"),
        ]
        analyze_fn, create_fn, flag_key = analysis_methods[idx % len(analysis_methods)]
        analysis = analyze_fn(repository)
        if not analysis.get(flag_key):
            return {"repository": repository, "action": idx + 1, "skipped": True, "reason": "no_findings"}

        result = create_fn(repository, analysis)
        return {"repository": repository, "action": idx + 1, "opencode": result, "task_type": create_fn.__name__}
