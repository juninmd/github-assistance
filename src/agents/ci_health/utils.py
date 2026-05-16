"""Utility functions for CI Health Agent."""
from collections.abc import Callable
from typing import Any

from github.Repository import Repository

def run_opencode_remediation(agent: Any, repo: Any, failures_text: str) -> dict[str, Any] | None:
    """Use opencode (free model) to create a PR fixing failing workflows."""
    instructions = (
        f"Repository: {repo.full_name}\n"
        "Task: Fix failing GitHub Actions workflows detected in the last 24h.\n"
        f"Failures:\n{failures_text}\n\n"
        "Required process:\n"
        "- Use opencode free-tier model.\n"
        "- Apply minimal safe fixes in workflow/config/code related to these failures.\n"
        "- Ensure files are valid and consistent.\n"
        "- Commit, push, and open a pull request."
    )
    try:
        result = agent.run_opencode_on_repo(
            repository=repo.full_name,
            instructions=instructions,
            title="Fix GitHub Actions failures",
        )
        if result.get("status") == "success":
            return {
                "repository": repo.full_name,
                "status": "pr_opened",
                "pr_url": result.get("pr_url"),
                "branch": result.get("branch"),
            }
        return {
            "repository": repo.full_name,
            "status": result.get("status", "failed"),
            "error": result.get("error") if result.get("error") is not None else result.get("stderr"),
        }
    except Exception as exc:
        agent.log(f"Failed opencode remediation in {repo.full_name}: {exc}", "WARNING")
        return None

def remediate_pipeline(agent: Any, repo: Any, failures: list[dict[str, str]]) -> dict[str, Any] | None:
    """Attempt to remediate a failing CI pipeline by opening an opencode PR."""
    failures_text = "\n".join(
        [f"- {f['name']} ({f['conclusion']}): {f['url']}" for f in failures]
    )
    return run_opencode_remediation(agent, repo, failures_text)
