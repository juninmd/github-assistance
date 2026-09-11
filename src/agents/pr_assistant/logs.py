"""Collect failed GitHub Actions logs / check-run annotations for the AI fixer."""

from __future__ import annotations

import os
import re
from typing import Any

import requests

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

_ERROR_CONTEXT_LINES = 25
_MAX_LINES_PER_JOB = 200
_MAX_LOG_CHARS = 12000
_LOG_REQUEST_TIMEOUT = 30
_FAILING_CONCLUSIONS = ("failure", "timed_out", "action_required")


def _clean_log_line(line: str) -> str:
    line = _ANSI_RE.sub("", line)
    line = _LOG_TIMESTAMP_RE.sub("", line)
    return line.rstrip()


def _tail_job_log(raw: str) -> str:
    """Extract the actual error context from a job log (noise-filtered)."""
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
    return [r for r in runs if r.conclusion in _FAILING_CONCLUSIONS]


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
            if job.conclusion not in _FAILING_CONCLUSIONS:
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
        if check_run.conclusion not in _FAILING_CONCLUSIONS:
            continue
        names.append(check_run.name or "check")
        summary = _check_run_summary(check_run)
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


def _check_run_summary(check_run) -> str:
    output = check_run.output
    if not output:
        return "No details"
    if isinstance(output, dict):
        return output.get("summary") or "No details"
    return getattr(output, "summary", None) or "No details"


def get_pipeline_error_logs(pr, token: str | None = None) -> dict[str, Any]:
    """Collect failed GitHub Actions error logs for the PR head commit."""
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
    seen: set[str] = set()
    unique_names = [n for n in names if not (n in seen or seen.add(n))]
    return {"logs": logs, "failed_checks": unique_names}
