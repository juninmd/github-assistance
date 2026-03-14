"""Pipeline status checks for PR Assistant."""
import re
from typing import Any


_COVERAGE_RE = re.compile(r"coverage[^0-9]{0,5}(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)


def _extract_coverage(text: str | None) -> float | None:
    """Extract a coverage percentage from text if present."""
    if not text:
        return None
    match = _COVERAGE_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def check_pipeline_status(pr) -> dict[str, Any]:
    """Check CI/CD pipeline status of the latest commit on a PR.

    Returns:
        Dict with keys: state, failed_checks, description, coverage (optional)
    """
    try:
        repo = pr.base.repo
        commit = repo.get_commit(pr.head.sha)

        # 1. Traditional commit statuses
        combined = commit.get_combined_status()
        state = combined.state

        # PyGithub defaults to "pending" if there are no traditional statuses.
        # If there are no statuses, we assume success unless check runs prove otherwise.
        if state == "pending" and combined.total_count == 0:
            state = "success"

        failed_checks: list[dict[str, str]] = []
        coverage: list[dict[str, Any]] = []
        if state in ("failure", "error"):
            for status in combined.statuses:
                if status.state in ("failure", "error"):
                    failed_checks.append({
                        "context": status.context,
                        "description": status.description or "No description",
                        "url": status.target_url or "",
                    })

        # Try to extract coverage info from traditional statuses (if any)
        for status in combined.statuses:
            cov = _extract_coverage(status.description)
            if cov is not None:
                coverage.append({"check": status.context, "coverage": cov})

        # 2. Check Runs (GitHub Actions)
        check_runs = commit.get_check_runs()
        for check_run in check_runs:
            # Extract coverage info from check run output (optional)
            if check_run.output and isinstance(check_run.output, dict):
                cov = _extract_coverage(check_run.output.get("summary"))
                if cov is not None:
                    coverage.append({"check": check_run.name, "coverage": cov})

            if check_run.conclusion in ("failure", "timed_out", "cancelled", "action_required"):
                state = "failure"
                failed_checks.append({
                    "context": check_run.name,
                    "description": check_run.output.get("summary", "No details") if check_run.output else "No details",
                    "url": check_run.html_url or "",
                })
            elif check_run.status != "completed" and state == "success":
                state = "pending"

        result = {"state": state, "failed_checks": failed_checks, "description": f"Pipeline state: {state}"}
        if coverage:
            result["coverage"] = coverage
        return result

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
