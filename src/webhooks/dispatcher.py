"""Route GitHub webhook events to durable PR automation jobs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from src.config.priorities import Priorities
from src.config.settings import Settings
from src.queue.store import JobStore
from src.run_agent import run_agent
from src.utils.logger import get_logger
from src.webhooks.auth import GitHubAppAuth

_TRANSIENT_BLOCKS = ("mergeable_state_unknown", "refresh_failed")

_log = get_logger("webhook-dispatcher")


def extract_pr_refs(event: str, payload: dict[str, Any]) -> list[str]:
    repository = payload.get("repository", {}).get("full_name")
    if not repository:
        return []
    numbers: set[int] = set()
    if event in {"pull_request", "pull_request_review"}:
        number = payload.get("pull_request", {}).get("number") or payload.get("number")
        if isinstance(number, int):
            numbers.add(number)
    elif event == "issue_comment" and payload.get("issue", {}).get("pull_request"):
        number = payload.get("issue", {}).get("number")
        if isinstance(number, int):
            numbers.add(number)
    elif event == "check_suite":
        numbers.update(_pull_numbers(payload.get("check_suite", {}).get("pull_requests", [])))
    elif event == "workflow_run":
        numbers.update(_pull_numbers(payload.get("workflow_run", {}).get("pull_requests", [])))
    return [f"{repository}#{number}" for number in sorted(numbers)]


def enqueue_pr(settings: Settings, pr_ref: str) -> bool:
    """Persist a PR job durably (idempotent per pr_ref)."""
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    repo = pr_ref.split("#", 1)[0]
    priority = Priorities(settings.priorities_path).priority_for(pr_ref)
    _job_id, created = store.enqueue(
        "pr",
        pr_ref,
        {"mode": settings.automation_mode, "source": "manual"},
        priority=priority,
        repo=repo,
    )
    _log.info("PR job enqueued", pr_ref=pr_ref, created=created)
    return True


def make_pr_handler(
    settings: Settings, max_attempts: int = 3
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build the durable-worker handler for PR jobs.

    Observe mode records without external effects; autonomous mode runs the
    PR Assistant agent for the specific PR.
    """

    def handle(job: dict[str, Any]) -> dict[str, Any]:
        pr_ref = job["key"]
        payload = job.get("payload") or {}
        mode = payload.get("mode") or settings.automation_mode
        result: dict[str, Any] = {"action": "observed"}
        if mode != "autonomous":
            return {
                "status": "succeeded",
                "decision": "observed",
                "next_action": "observe",
                "result": result,
            }
        token = _installation_token(settings)
        agent_settings = replace(settings, github_token=token)
        result = run_agent("pr-assistant", agent_settings, pr_ref=pr_ref)
        if result.get("error"):
            return {
                "status": "failed",
                "error": str(result["error"]),
                "decision": "failed",
                "next_action": "retry",
                "result": result,
            }
        transient = [
            b["reason"]
            for b in result.get("blocked", [])
            if str(b.get("reason", "")).startswith(_TRANSIENT_BLOCKS)
        ]
        if transient:
            # No webhook fires when these clear, so let queue backoff re-run the job.
            return {
                "status": "failed",
                "error": f"transient block: {', '.join(transient)}",
                "decision": "blocked",
                "next_action": "retry",
                "result": result,
            }
        run_status = (result.get("_run_result") or {}).get("status")
        return {
            "status": "succeeded",
            "decision": run_status or result.get("status", "succeeded"),
            "next_action": "done",
            "sha": result.get("sha"),
            "task_id": result.get("task_id"),
            "result": result,
        }

    handle.max_attempts = max_attempts
    return handle


def _installation_token(settings: Settings) -> str:
    if not (
        settings.github_app_id
        and settings.github_installation_id
        and settings.github_app_private_key_path
    ):
        raise ValueError("GitHub App authentication is incomplete")
    return GitHubAppAuth(
        settings.github_app_id,
        settings.github_installation_id,
        settings.github_app_private_key_path,
    ).installation_token()


def _pull_numbers(items: list[dict[str, Any]]) -> set[int]:
    return {item["number"] for item in items if isinstance(item.get("number"), int)}
