"""Pipeline status checks for PR Assistant."""
import re
from typing import Any

_COVERAGE_RE = re.compile(r"coverage[^0-9]{0,5}(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)

# Check names containing these substrings are non-blocking (quality/reporting tools).
# Failures from these checks will NOT block the merge.
_IGNORABLE_CHECK_PATTERNS = (
    "sonar",
    "quality gate",
    "codex",
    "codecov",
    "coveralls",
    "deepsource",
    "code climate",
    "codacy",
    "snyk",
)

# If a failed check's description contains any of these substrings it is a
# billing / infrastructure issue unrelated to code quality — treat as success.
_BILLING_PHRASES = (
    "recent account payments have failed",
    "spending limit needs to be increased",
    "you have reached your codex usage limits",
    "minutes limit",
    "billing",
)


def _is_ignorable(name: str) -> bool:
    low = name.lower()
    return any(pat in low for pat in _IGNORABLE_CHECK_PATTERNS)


def _is_billing_failure(description: str) -> bool:
    low = (description or "").lower()
    return any(phrase in low for phrase in _BILLING_PHRASES)


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


def _check_run_summary(check_run) -> str:
    """Safely get a summary string from a check run output (object or dict)."""
    output = check_run.output
    if not output:
        return "No details"
    if isinstance(output, dict):
        return output.get("summary") or "No details"
    return getattr(output, "summary", None) or "No details"


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

        failed_checks: list[dict[str, str]] = []
        coverage: list[dict[str, Any]] = []
        is_pending = False

        for status in combined.statuses:
            if not _is_ignorable(status.context):
                if status.state in ("failure", "error"):
                    desc = status.description or "No description"
                    if not _is_billing_failure(desc):
                        failed_checks.append({
                            "context": status.context,
                            "description": desc,
                            "url": status.target_url or "",
                        })
                elif status.state == "pending":
                    is_pending = True

            cov = _extract_coverage(status.description)
            if cov is not None:
                coverage.append({"check": status.context, "coverage": cov})

        # 2. Check Runs (GitHub Actions)
        check_runs = commit.get_check_runs()
        for check_run in check_runs:
            # Extract coverage info from check run output
            summary = _check_run_summary(check_run)
            cov = _extract_coverage(summary)
            if cov is not None:
                coverage.append({"check": check_run.name, "coverage": cov})

            if _is_ignorable(check_run.name):
                continue

            # "cancelled" is not treated as a blocking failure — it usually means
            # another job failed and cancelled the rest of the workflow.
            if check_run.conclusion in ("failure", "timed_out", "action_required"):
                if _is_billing_failure(summary):
                    continue
                failed_checks.append({
                    "context": check_run.name,
                    "description": summary,
                    "url": check_run.html_url or "",
                })
            elif check_run.status != "completed":
                is_pending = True

        if failed_checks:
            state = "failure"
        elif is_pending:
            state = "pending"
        else:
            state = "success"

        result = {"state": state, "failed_checks": failed_checks, "description": f"Pipeline state: {state}"}
        if coverage:
            result["coverage"] = coverage
        return result

    except Exception as e:
        return {"state": "unknown", "failed_checks": [], "description": f"Error checking pipeline: {e}"}


def has_existing_failure_comment(pr, issue_comments: list | None = None) -> bool:
    """Check if a failure comment was already posted (avoid spam)."""
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        return any("Pipeline Failure Detected" in (c.body or "") for c in comments)
    except Exception:
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
