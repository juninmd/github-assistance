"""Pipeline status evaluation for the current PR head SHA.

Every check/status is judged against the head SHA actually being merged.
Failing, pending, unknown, cancelled and absent evidence never count as
success. There is no check-name or billing exemption.
"""

from __future__ import annotations

import re
from typing import Any

from src.agents.utils import build_origin_metadata

_COVERAGE_RE = re.compile(r"coverage[^0-9]{0,5}(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)

_FAILING_CONCLUSIONS = {"failure", "timed_out", "action_required", "startup_failure", "stale"}
_CANCELLED_CONCLUSIONS = {"cancelled"}
_INCONCLUSIVE_CONCLUSIONS = {"neutral", "skipped"}
_FAILING_STATES = {"failure", "error"}

# Matches GitHub Actions refusing to start a job for billing reasons (unpaid
# invoice, spending limit). This never counts as evidence the code is safe —
# the job simply never ran — so it still blocks merge like any other failure;
# it is only classified separately so PR Assistant can alert with the right
# root cause (fix billing) instead of asking the author to fix their code.
_BILLING_RE = re.compile(
    r"account payments have failed|spending limit needs to be increased|"
    r"exceeded.{0,15}(spending|usage) limit",
    re.IGNORECASE,
)


def _is_billing_failure(text: str | None) -> bool:
    return bool(text) and bool(_BILLING_RE.search(text))


class _Buckets:
    def __init__(self) -> None:
        self.failed: list[dict[str, str]] = []
        self.pending: list[str] = []
        self.cancelled: list[dict[str, str]] = []
        self.success: list[str] = []
        self.coverage: list[dict[str, Any]] = []
        self.billing: list[str] = []
        self.total = 0

    def success_check(self, name: str) -> None:
        self.success.append(name)
        self.total += 1

    def fail(self, name: str, description: str, url: str) -> None:
        self.failed.append({"context": name, "description": description, "url": url})
        if _is_billing_failure(description):
            self.billing.append(name)
        self.total += 1

    def cancel(self, name: str, description: str) -> None:
        self.cancelled.append({"context": name, "description": description, "url": ""})
        self.total += 1


def _check_run_summary(check_run) -> str:
    output = check_run.output
    if not output:
        return "No details"
    if isinstance(output, dict):
        return output.get("summary") or "No details"
    return getattr(output, "summary", None) or "No details"


def _process_commit_statuses(combined, buckets: _Buckets) -> None:
    for status in combined.statuses:
        buckets.total += 1
        desc = status.description or "No description"
        cov = _extract_coverage(desc)
        if cov is not None:
            buckets.coverage.append({"check": status.context, "coverage": cov})
        if status.state in _FAILING_STATES:
            buckets.fail(status.context, desc, status.target_url or "")
        elif status.state == "pending":
            buckets.pending.append(status.context)
        else:
            buckets.success_check(status.context)


def _process_check_runs(check_runs, buckets: _Buckets) -> None:
    for check_run in check_runs:
        summary = _check_run_summary(check_run)
        cov = _extract_coverage(summary)
        if cov is not None:
            buckets.coverage.append({"check": check_run.name, "coverage": cov})
        buckets.total += 1
        if check_run.conclusion in _FAILING_CONCLUSIONS:
            buckets.fail(check_run.name, summary, check_run.html_url or "")
        elif check_run.conclusion in _CANCELLED_CONCLUSIONS:
            buckets.cancel(check_run.name, summary)
        elif check_run.status != "completed" or check_run.conclusion in _INCONCLUSIVE_CONCLUSIONS:
            buckets.pending.append(check_run.name)
        else:
            buckets.success_check(check_run.name)


def _extract_coverage(text: str | None) -> float | None:
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
    """Evaluate pipeline evidence for ``pr.head.sha``."""
    try:
        repo = pr.base.repo
        commit = repo.get_commit(pr.head.sha)
        combined = commit.get_combined_status()
        buckets = _Buckets()
        _process_commit_statuses(combined, buckets)
        _process_check_runs(commit.get_check_runs(), buckets)

        state = "success"
        if buckets.failed or buckets.cancelled:
            state = "failure"
        elif buckets.pending or buckets.total == 0:
            state = "pending"
        result: dict[str, Any] = {
            "state": state,
            "failed_checks": buckets.failed,
            "pending_checks": buckets.pending,
            "cancelled_checks": buckets.cancelled,
            "success_checks": [{"context": name} for name in buckets.success],
            "has_evidence": buckets.total > 0,
            "checks": {
                "total": buckets.total,
                "success": len(buckets.success),
                "failed": len(buckets.failed),
                "pending": len(buckets.pending),
                "cancelled": len(buckets.cancelled),
            },
            "description": f"Pipeline state: {state}",
            # True only when every failed check is a GitHub Actions billing
            # refusal (job never ran) — never when a real check also failed.
            "billing_checks": buckets.billing,
            "billing_blocked": bool(buckets.failed) and len(buckets.billing) == len(buckets.failed),
        }
        if buckets.coverage:
            result["coverage"] = buckets.coverage
        return result
    except Exception as e:
        return {
            "state": "unknown",
            "failed_checks": [],
            "pending_checks": [],
            "cancelled_checks": [],
            "success_checks": [],
            "has_evidence": False,
            "checks": {"total": 0, "success": 0, "failed": 0, "pending": 0, "cancelled": 0},
            "billing_checks": [],
            "billing_blocked": False,
            "description": f"Error checking pipeline: {e}",
        }


def has_existing_failure_comment(pr, issue_comments: list | None = None) -> bool:
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        return any("Pipeline Failure Detected" in (c.body or "") for c in comments)
    except Exception:
        return False


def has_existing_billing_comment(pr, issue_comments: list | None = None) -> bool:
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        return any("<!-- pipeline-billing-blocked -->" in (c.body or "") for c in comments)
    except Exception:
        return False


def build_billing_blocked_comment(pr, billing_checks: list[str]) -> str:
    author = pr.user.login if pr.user else "contributor"
    checks_text = ", ".join(f"`{c}`" for c in billing_checks) or "the CI check"
    return (
        "<!-- pipeline-billing-blocked -->\n"
        "🧾 **CI Blocked by GitHub Actions Billing**\n\n"
        f"Hi @{author}, {checks_text} did not run — GitHub reports the account's "
        "Actions billing failed (unpaid invoice or spending limit reached), not a "
        "problem with this PR's code.\n\n"
        "This never counted as a passing check, so the merge is on hold: a job that "
        "never ran is not evidence the code is safe.\n\n"
        "**To unblock:** fix billing in the repository owner's GitHub "
        "**Settings → Billing & plans**, then re-run the failed workflow — merge "
        "will proceed automatically once it goes green.\n\n"
        f"{build_origin_metadata('pr_assistant')}"
    )


def build_failure_comment(pr, failed_checks: list[dict[str, str]]) -> str:
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
        "Thank you! 🙏\n\n"
        f"{build_origin_metadata('pr_assistant')}"
    )


# Backward-compatible re-exports (log collection moved to logs.py).
from src.agents.pr_assistant.logs import get_pipeline_error_logs  # noqa: E402,F401

__all__ = [
    "check_pipeline_status",
    "has_existing_failure_comment",
    "has_existing_billing_comment",
    "build_failure_comment",
    "build_billing_blocked_comment",
    "get_pipeline_error_logs",
]
