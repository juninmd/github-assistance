"""Pipeline status checks for PR Assistant."""
from typing import Any


def check_pipeline_status(pr) -> dict[str, Any]:
    """Check CI/CD pipeline status of the latest commit on a PR.

    Returns:
        Dict with keys: state, failed_checks, description
    """
    try:
        repo = pr.base.repo
        commit = repo.get_commit(pr.head.sha)
        combined = commit.get_combined_status()
        state = combined.state

        failed_checks: list[dict[str, str]] = []
        if state in ("failure", "error"):
            for status in combined.statuses:
                if status.state in ("failure", "error"):
                    failed_checks.append({
                        "context": status.context,
                        "description": status.description or "No description",
                        "url": status.target_url or "",
                    })

        # Also check GitHub Check Runs (Actions)
        check_runs = commit.get_check_runs()
        for check_run in check_runs:
            if check_run.conclusion in ("failure", "timed_out", "cancelled", "action_required"):
                failed_checks.append({
                    "context": check_run.name,
                    "description": check_run.output.get("summary", "No details") if check_run.output else "No details",
                    "url": check_run.html_url or "",
                })
            if check_run.status != "completed" and state == "success":
                state = "pending"

        return {"state": state, "failed_checks": failed_checks, "description": f"Pipeline state: {state}"}

    except Exception as e:
        return {"state": "unknown", "failed_checks": [], "description": f"Error checking pipeline: {e}"}


def has_existing_failure_comment(pr) -> bool:
    """Check if a failure comment was already posted (avoid spam)."""
    try:
        for comment in pr.get_issue_comments():
            if "Pipeline Failure Detected" in (comment.body or ""):
                return True
    except Exception:
        pass
    return False


def build_failure_comment(pr, failed_checks: list[dict[str, str]]) -> str:
    """Build a formatted comment about pipeline failures."""
    failures_text = "\n".join(
        f"- **{check['context']}**: {check['description']}"
        + (f" ([details]({check['url']}))" if check.get("url") else "")
        for check in failed_checks
    )
    author = pr.user.login if pr.user else "contributor"
    return (
        "❌ **Pipeline Failure Detected**\n\n"
        f"Hi @{author}, the CI/CD pipeline for this PR has failed.\n\n"
        f"**Failure Details:**\n{failures_text}\n\n"
        "Please review the errors above and push corrections to resolve these issues.\n"
        "Once all checks pass, I'll be able to merge this PR automatically.\n\n"
        "Thank you! 🙏"
    )
