"""Utility functions for CI Health Agent."""

from typing import Any


def create_vibe_code_remediation(agent: Any, repo: Any, failures_text: str) -> dict[str, Any] | None:
    """Create a Vibe-Code task that uses the opencode agent for CI remediation."""
    instructions = (
        f"Repository: {repo.full_name}\n"
        "Task: Fix failing GitHub Actions workflows detected in the last 24h.\n"
        f"Failures:\n{failures_text}\n\n"
        "Required process:\n"
        "- Apply minimal safe fixes in workflow/config/code related to these failures.\n"
        "- Ensure files are valid and consistent.\n"
        "- Commit, push, and open a pull request from vibe-code."
    )
    try:
        result = agent.create_opencode_task(
            repository=repo.full_name,
            instructions=instructions,
            title="Fix GitHub Actions failures",
        )
        if result.get("status") == "task_created":
            return {
                "repository": repo.full_name,
                "status": "task_created",
                "task_id": result.get("task_id"),
                "task_url": result.get("task_url"),
            }
        return {
            "repository": repo.full_name,
            "status": result.get("status", "failed"),
            "error": result.get("error")
            if result.get("error") is not None
            else result.get("stderr"),
        }
    except Exception as exc:
        agent.log(f"Failed opencode remediation in {repo.full_name}: {exc}", "WARNING")
        return None


def remediate_pipeline(
    agent: Any, repo: Any, failures: list[dict[str, str]]
) -> dict[str, Any] | None:
    """Attempt to remediate a failing CI pipeline with a Vibe-Code opencode task."""
    failures_text = "\n".join([f"- {f['name']} ({f['conclusion']}): {f['url']}" for f in failures])
    return create_vibe_code_remediation(agent, repo, failures_text)
