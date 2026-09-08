"""Queryable view over why a PR was not merged (CLI/API)."""

from __future__ import annotations

from typing import Any

from src.agents.pr_assistant.merge_policy import MergePolicy
from src.agents.pr_assistant.pipeline import check_pipeline_status
from src.config.autonomy_policy import AutonomyPolicy
from src.config.settings import Settings
from src.github_client import GithubClient
from src.queue.store import JobStore


def job_history(settings: Settings, pr_ref: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Return the durable job history for a PR (or the most recent jobs)."""
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    jobs = store.list_jobs(kind="pr", limit=limit)
    if pr_ref:
        return [j for j in jobs if j["key"] == pr_ref]
    return jobs


def explain_pr(settings: Settings, pr_ref: str) -> dict[str, Any]:
    """Explain why a PR was not merged using policy + live pipeline evidence."""
    repo = pr_ref.split("#", 1)[0]
    try:
        number = int(pr_ref.rsplit("#", 1)[1])
    except (IndexError, ValueError):
        return {"pr_ref": pr_ref, "reasons": ["invalid_pr_ref"]}

    autonomy = AutonomyPolicy(settings.autonomy_policy_path).for_repository(repo)
    history = job_history(settings, pr_ref)

    try:
        client = GithubClient(settings.github_token)
        pr = client.get_repo(repo).get_pull(number)
    except Exception as e:
        return {
            "pr_ref": pr_ref,
            "reasons": [f"pr_unavailable: {e}"],
            "autonomy_mode": autonomy.mode,
            "job_history": history,
        }

    status = check_pipeline_status(pr)
    decision = MergePolicy().evaluate(
        status=status,
        expected_sha=None,
        current_sha=pr.head.sha,
        autonomy=autonomy,
    )
    reasons = list(decision.reasons)
    if pr.mergeable is False:
        reasons.append("merge_conflicts")
    if pr.merged_at:
        reasons.append("already_merged")

    return {
        "pr_ref": pr_ref,
        "state": pr.state,
        "merged": bool(pr.merged_at),
        "head_sha": pr.head.sha,
        "autonomy_mode": autonomy.mode,
        "pipeline_state": status["state"],
        "reasons": reasons,
        "decision": decision.action,
        "job_history": history,
    }
