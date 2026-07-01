"""GitHub Actions workflow policy checks.

Scheduled (``on: schedule: - cron:``) workflows are **prohibited** across the
portfolio. A cron trigger fires on GitHub-hosted runners forever — even when
there is no pending work and even on idle/abandoned repositories — silently
burning Actions minutes and inflating the bill. Event-driven triggers
(``push``, ``pull_request``, ``workflow_dispatch``, ``workflow_call``,
repository/webhook events) cost nothing while idle and should always be
preferred. Genuinely periodic jobs belong on a single, centrally-managed
orchestrator, not scattered cron entries in every repo.

This module is intentionally dependency-free (no PyYAML) so it can run inside
the gitleaks scan container and as a lightweight CI guard. ``cron:`` only ever
appears under a ``schedule:`` trigger in an Actions workflow, so a line-based
scan is both sufficient and precise (``dependabot.yml`` uses ``interval:``, not
``cron:``, and is therefore never matched).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Relative location of workflow definitions inside a repository checkout.
WORKFLOW_DIR = ".github/workflows"
_WORKFLOW_GLOBS = ("*.yml", "*.yaml")

# The one sanctioned scheduled workflow: the portfolio orchestrator entry point.
# Every other cron trigger is a policy violation. Keep this list as short as
# possible — ideally empty.
APPROVED_SCHEDULED_WORKFLOWS = frozenset({"daily-project-creator.yml"})

# The one sanctioned scheduled workflow: the portfolio orchestrator entry point.
# Every other cron trigger is a policy violation. Keep this list as short as
# possible — ideally empty.
APPROVED_SCHEDULED_WORKFLOWS = frozenset({"daily-project-creator.yml"})

# The one sanctioned scheduled workflow: the portfolio orchestrator entry point.
# Every other cron trigger is a policy violation. Keep this list as short as
# possible — ideally empty.
APPROVED_SCHEDULED_WORKFLOWS = frozenset({"daily-project-creator.yml"})

# Matches e.g. `    - cron: "0 9 * * *"  # daily` and captures the expression.
_CRON_LINE = re.compile(r"^\s*-?\s*cron\s*:\s*(?P<expr>.+?)\s*$", re.IGNORECASE)


def _clean_expr(raw: str) -> str:
    """Strip surrounding quotes and trailing ``# comments`` from a cron value."""
    expr = raw.strip()
    quote = expr[:1]
    if quote in {'"', "'"}:
        # Quoted value: take everything up to the matching closing quote and
        # discard any trailing inline comment.
        closing = expr.find(quote, 1)
        if closing != -1:
            return expr[1:closing].strip()
        expr = expr[1:]
    elif "#" in expr:
        expr = expr.split("#", 1)[0].strip()
    return expr


def scan_workflow_text(text: str, file: str = "") -> list[dict[str, Any]]:
    """Return cron-trigger violations found in a single workflow's *text*.

    Each violation is ``{"file", "line", "cron"}``. A workflow may declare
    several cron entries, so multiple violations can come from one file.
    """
    violations: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        match = _CRON_LINE.match(line)
        if not match:
            continue
        violations.append(
            {
                "file": file,
                "line": index,
                "cron": _clean_expr(match.group("expr")),
            }
        )
    return violations


def detect_cron_workflows(
    repo_dir: str | Path,
    approved: set[str] | frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Scan ``<repo_dir>/.github/workflows`` for prohibited cron triggers.

    *approved* is an optional set of workflow **file names** (e.g.
    ``{"daily-project-creator.yml"}``) that are explicitly sanctioned and
    excluded from the result — use it only for a single, deliberately-managed
    orchestrator. Defaults to ``APPROVED_SCHEDULED_WORKFLOWS``.
    Returns a flat, sorted list of ``{"file", "line", "cron"}``
    violations with repo-relative file paths.
    """
    if approved is None:
        approved = APPROVED_SCHEDULED_WORKFLOWS
    workflows_path = Path(repo_dir) / WORKFLOW_DIR
    if not workflows_path.is_dir():
        return []

    violations: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for pattern in _WORKFLOW_GLOBS:
        for workflow_file in workflows_path.glob(pattern):
            if workflow_file in seen or not workflow_file.is_file():
                continue
            seen.add(workflow_file)
            if workflow_file.name in approved:
                continue
            try:
                text = workflow_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            relative = f"{WORKFLOW_DIR}/{workflow_file.name}"
            violations.extend(scan_workflow_text(text, file=relative))

    violations.sort(key=lambda item: (item["file"], item["line"]))
    return violations
