#!/usr/bin/env python3
"""Fail CI if a prohibited cron-scheduled GitHub Actions workflow is added.

Scheduled (``on: schedule: - cron:``) workflows run on GitHub-hosted runners
forever — even on idle repos — silently burning Actions minutes. This guard
keeps the policy enforced in *this* repository; the Security Scanner agent
enforces it across the rest of the portfolio.

A single, deliberately-managed orchestrator may be allowlisted below. Run with
``--list`` to print detected cron triggers without failing.

Usage:
    python scripts/check_no_cron_workflows.py [--repo-dir .] [--list]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make ``src`` importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.security_scanner.workflow_policy import (
    APPROVED_SCHEDULED_WORKFLOWS,
    detect_cron_workflows,
)
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", default=".", help="Repository root (default: .)")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List every cron trigger (including approved) without failing",
    )
    args = parser.parse_args()

    approved = frozenset() if args.list else APPROVED_SCHEDULED_WORKFLOWS
    violations = detect_cron_workflows(args.repo_dir, approved=approved)

    if not violations:
        print("✅ No prohibited cron-scheduled workflows found.")
        return 0

    if args.list:
        print(f"Found {len(violations)} cron trigger(s):")
        for v in violations:
            note = " (approved)" if Path(v["file"]).name in APPROVED_SCHEDULED_WORKFLOWS else ""
            print(f"  {v['file']}:{v['line']}  cron: {v['cron']}{note}")
        return 0

    print(f"❌ {len(violations)} prohibited cron-scheduled workflow trigger(s) found:\n")
    for v in violations:
        print(f"  {v['file']}:{v['line']}  ->  cron: {v['cron']}")
    print(
        "\nScheduled (cron) GitHub Actions are prohibited because they consume "
        "runner minutes continuously, even on idle repos.\n"
        "Use `workflow_dispatch` or event-driven triggers instead, or delegate "
        "periodic work to the central orchestrator."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
