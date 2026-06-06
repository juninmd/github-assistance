"""Route GitHub webhook events to targeted PR automation."""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any

from src.config.settings import Settings
from src.run_agent import run_agent
from src.utils.logger import get_logger
from src.webhooks.auth import GitHubAppAuth

_log = get_logger("webhook-dispatcher")
_active_prs: set[str] = set()
_lock = threading.Lock()


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


def dispatch_pr(settings: Settings, pr_ref: str) -> None:
    with _lock:
        if pr_ref in _active_prs:
            _log.info("PR processing already active", pr_ref=pr_ref)
            return
        _active_prs.add(pr_ref)
    try:
        token = _installation_token(settings)
        agent_settings = replace(settings, github_token=token)
        result = run_agent("pr-assistant", agent_settings, pr_ref=pr_ref)
        _log.info("PR processing completed", pr_ref=pr_ref, error=result.get("error"))
    except Exception as exc:
        _log.error("PR processing failed", pr_ref=pr_ref, error=str(exc))
    finally:
        with _lock:
            _active_prs.discard(pr_ref)


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
