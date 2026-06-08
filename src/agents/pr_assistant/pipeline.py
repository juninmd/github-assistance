"""Pipeline status checks for PR Assistant."""

import os
import re
from typing import Any

import requests

_COVERAGE_RE = re.compile(r"coverage[^0-9]{0,5}(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)

# GitHub Actions log lines are prefixed with an ISO timestamp; strip it for the AI.
_LOG_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Runner/security-agent journal noise that buries the real error (e.g. StepSecurity
# harden-runner dumps its whole journal during post-job cleanup).
_LOG_NOISE_RE = re.compile(
    r"(agentservice\[|systemd\[\d|sudo\[\d|pam_unix\(|module=armour|\[armour-cdr\]"
    r"|Download action repository|Prepare all required actions|##\[endgroup\]"
    r"|^\s*\*\s+\[new branch\].*->\s+origin/)"
)
# Lines that mark an actual failure — we keep these and the context leading up to them.
_ERROR_MARKER_RE = re.compile(
    r"(##\[error\]|\berror\[|\berror:|\bERROR\b|\bFAILED?\b|Traceback|exception|panicked)",
    re.IGNORECASE,
)

# How much error context to feed the fixer. Keeps prompts (and token cost) bounded.
_ERROR_CONTEXT_LINES = 25
_MAX_LINES_PER_JOB = 200
_MAX_LOG_CHARS = 12000
_LOG_REQUEST_TIMEOUT = 30

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
            if status.state in ("failure", "error"):
                desc = status.description or "No description"
                if not _is_billing_failure(desc):
                    failed_checks.append(
                        {
                            "context": status.context,
                            "description": desc,
                            "url": status.target_url or "",
                        }
                    )
            elif status.state == "pending" and not _is_ignorable(status.context):
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

            # "cancelled" is not treated as a blocking failure — it usually means
            # another job failed and cancelled the rest of the workflow.
            if check_run.conclusion in ("failure", "timed_out", "action_required"):
                if _is_billing_failure(summary):
                    continue
                failed_checks.append(
                    {
                        "context": check_run.name,
                        "description": summary,
                        "url": check_run.html_url or "",
                    }
                )
            elif check_run.status != "completed" and not _is_ignorable(check_run.name):
                is_pending = True

        if failed_checks:
            state = "failure"
        elif is_pending:
            state = "pending"
        else:
            state = "success"

        result = {
            "state": state,
            "failed_checks": failed_checks,
            "description": f"Pipeline state: {state}",
        }
        if coverage:
            result["coverage"] = coverage
        return result

    except Exception as e:
        return {
            "state": "unknown",
            "failed_checks": [],
            "description": f"Error checking pipeline: {e}",
        }


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


def _clean_log_line(line: str) -> str:
    line = _ANSI_RE.sub("", line)
    line = _LOG_TIMESTAMP_RE.sub("", line)
    return line.rstrip()


def _tail_job_log(raw: str) -> str:
    """Extract the actual error context from a job log.

    Filters runner/security-agent journal noise, then keeps windows of lines
    leading up to each error marker. Falls back to the tail when no marker is
    found (e.g. a bare non-zero exit).
    """
    lines = [_clean_log_line(line) for line in raw.splitlines()]
    lines = [line for line in lines if line and not _LOG_NOISE_RE.search(line)]
    if not lines:
        return ""

    error_idx = [i for i, line in enumerate(lines) if _ERROR_MARKER_RE.search(line)]
    if not error_idx:
        return "\n".join(lines[-_MAX_LINES_PER_JOB:])

    keep: set[int] = set()
    for idx in error_idx:
        keep.update(range(max(0, idx - _ERROR_CONTEXT_LINES), min(len(lines), idx + 2)))
    selected = [lines[i] for i in sorted(keep)]
    return "\n".join(selected[-_MAX_LINES_PER_JOB:])


def _failed_workflow_runs(repo, head_sha: str) -> list:
    """Return failed/timed-out workflow runs for the PR head commit."""
    try:
        runs = list(repo.get_workflow_runs(head_sha=head_sha))
    except TypeError:
        # Older PyGithub without head_sha kwarg — filter manually.
        runs = [r for r in repo.get_workflow_runs() if getattr(r, "head_sha", None) == head_sha]
    return [r for r in runs if r.conclusion in ("failure", "timed_out", "action_required")]


def _download_job_log(repo, job_id: int, token: str) -> str | None:
    """Download a single job's log via the Actions REST API."""
    url = f"https://api.github.com/repos/{repo.full_name}/actions/jobs/{job_id}/logs"
    try:
        resp = requests.get(
            url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=_LOG_REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200 or not resp.text:
        return None
    return resp.text


def _logs_from_runs(repo, runs: list, token: str) -> tuple[list[str], list[str]]:
    """Collect cleaned failed-job logs and their names from workflow runs."""
    blocks: list[str] = []
    names: list[str] = []
    for run in runs:
        try:
            jobs = list(run.jobs())
        except Exception:
            continue
        for job in jobs:
            if job.conclusion not in ("failure", "timed_out", "action_required"):
                continue
            if _is_ignorable(job.name or ""):
                continue
            names.append(job.name or "job")
            raw = _download_job_log(repo, job.id, token)
            if not raw:
                continue
            tail = _tail_job_log(raw)
            if tail:
                blocks.append(f"### Job: {job.name}\n{tail}")
    return blocks, names


def _logs_from_check_runs(pr) -> tuple[list[str], list[str]]:
    """Fallback: build error context from check-run summaries and annotations."""
    blocks: list[str] = []
    names: list[str] = []
    try:
        commit = pr.base.repo.get_commit(pr.head.sha)
        check_runs = commit.get_check_runs()
    except Exception:
        return blocks, names
    for check_run in check_runs:
        if check_run.conclusion not in ("failure", "timed_out", "action_required"):
            continue
        if _is_ignorable(check_run.name or ""):
            continue
        summary = _check_run_summary(check_run)
        if _is_billing_failure(summary):
            continue
        names.append(check_run.name or "check")
        parts = [f"### Check: {check_run.name}", summary]
        try:
            annotations = list(check_run.get_annotations())
        except Exception:
            annotations = []
        for ann in annotations[:30]:
            path = getattr(ann, "path", "") or ""
            line = getattr(ann, "start_line", "") or ""
            message = getattr(ann, "message", "") or ""
            parts.append(f"{path}:{line} {message}".strip())
        blocks.append("\n".join(p for p in parts if p))
    return blocks, names


def get_pipeline_error_logs(pr, token: str | None = None) -> dict[str, Any]:
    """Collect failed GitHub Actions error logs for the PR head commit.

    Returns dict with keys: logs (str), failed_checks (list[str]).
    Prefers real job logs; falls back to check-run summaries/annotations.
    """
    token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    repo = pr.base.repo
    blocks: list[str] = []
    names: list[str] = []

    try:
        runs = _failed_workflow_runs(repo, pr.head.sha)
        if token and runs:
            blocks, names = _logs_from_runs(repo, runs, token)
    except Exception:
        blocks, names = [], []

    if not blocks:
        fb_blocks, fb_names = _logs_from_check_runs(pr)
        blocks = blocks or fb_blocks
        names = names or fb_names

    logs = "\n\n".join(blocks)
    if len(logs) > _MAX_LOG_CHARS:
        logs = logs[-_MAX_LOG_CHARS:]
    # De-duplicate names preserving order.
    seen: set[str] = set()
    unique_names = [n for n in names if not (n in seen or seen.add(n))]
    return {"logs": logs, "failed_checks": unique_names}
