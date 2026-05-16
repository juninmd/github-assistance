"""
Utility functions for Senior Developer Agent.
"""
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from os import getenv
from typing import Any

from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer
from src.agents.senior_developer.task_creator import SeniorDeveloperTaskCreator
from src.jules.client import JulesClient


def extract_session_datetime(session: dict[str, Any]) -> datetime | None:
    """Extract datetime from session dictionary."""
    created_at = session.get("createTime") or session.get("createdAt")
    if not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def is_same_day(session: dict[str, Any], target_date: datetime | None) -> bool:
    """Check if a session was created on a specific date in UTC-3."""
    created_at = session.get("createTime") or session.get("createdAt")
    if not created_at:
        return False
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return (dt.astimezone(UTC) - timedelta(hours=3)).date() == target_date
    except Exception:
        return False


def count_today_sessions_utc_minus_3(jules_client: JulesClient, log_func: Callable[..., None]) -> int:
    """Count how many Jules sessions were already created on the current UTC-3 day."""
    try:
        sessions = jules_client.list_sessions(page_size=200)
        now_date = (datetime.now(UTC) - timedelta(hours=3)).date()
        return sum(1 for s in sessions if is_same_day(s, now_date))
    except Exception as e:
        log_func(f"Failed to list session quota: {e}", "WARNING")
        return 0


def create_burst_task(
    repository: str,
    idx: int,
    analyzer: SeniorDeveloperAnalyzer,
    task_creator: SeniorDeveloperTaskCreator,
    log_func: Callable[..., None],
) -> dict[str, Any]:
    """Create one extra task using real analysis, rotating through analysis types."""
    analysis_methods = [
        (analyzer.analyze_security, task_creator.create_security_task, "needs_attention"),
        (analyzer.analyze_cicd, task_creator.create_cicd_task, "needs_improvement"),
        (analyzer.analyze_tech_debt, task_creator.create_tech_debt_task, "needs_attention"),
        (analyzer.analyze_modernization, task_creator.create_modernization_task, "needs_modernization"),
        (analyzer.analyze_performance, task_creator.create_performance_task, "needs_optimization"),
        (analyzer.analyze_roadmap_features, task_creator.create_feature_implementation_task, "has_features"),
    ]
    analyze_fn, create_fn, flag_key = analysis_methods[idx % len(analysis_methods)]
    analysis = analyze_fn(repository)
    if not analysis.get(flag_key):
        log_func(f"Burst #{idx+1}: no actionable findings for {repository} ({analyze_fn.__name__})")
        return {"repository": repository, "action": idx + 1, "skipped": True, "reason": "no_findings"}
    session = create_fn(repository, analysis)
    return {"repository": repository, "action": idx + 1, "session_id": session.get("id"), "task_type": create_fn.__name__}


def execute_burst_action(
    repositories: list[str],
    idx: int,
    analyzer: SeniorDeveloperAnalyzer,
    task_creator: SeniorDeveloperTaskCreator,
    log_func: Callable[..., None],
) -> dict[str, Any]:
    """Executes a single burst action."""
    repo = repositories[idx % len(repositories)]
    try:
        return create_burst_task(repo, idx, analyzer, task_creator, log_func)
    except Exception as e:
        return {"repository": repo, "action": idx + 1, "error": str(e)}


def run_end_of_day_session_burst(
    repositories: list[str],
    jules_client: JulesClient,
    analyzer: SeniorDeveloperAnalyzer,
    task_creator: SeniorDeveloperTaskCreator,
    log_func: Callable[..., None],
) -> list[dict[str, Any]]:
    """Run a configurable end-of-day burst to consume available Jules sessions."""
    max_actions = int(getenv("JULES_BURST_MAX_ACTIONS", "0"))
    trigger_hour = int(getenv("JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3", "18"))
    now_h = (datetime.now(UTC) - timedelta(hours=3)).hour

    if max_actions <= 0 or now_h < trigger_hour or not repositories:
        return []

    daily_limit = int(getenv("JULES_DAILY_SESSION_LIMIT", "100"))
    actions_to_run = min(max_actions, max(daily_limit - count_today_sessions_utc_minus_3(jules_client, log_func), 0))

    if actions_to_run <= 0:
        return []

    return [
        execute_burst_action(repositories, i, analyzer, task_creator, log_func)
        for i in range(actions_to_run)
    ]
