#!/usr/bin/env python3
"""Fail if any GitHub Actions workflow exists in this repository.

Policy: nothing runs on GitHub Actions — all periodic and event-driven work is
executed from the Kubernetes cluster (CronJobs/Jobs triggered by the webhook
receiver). A single workflow file in ``.github/workflows/`` is a policy
violation, cron-triggered or not.

Usage:
    python scripts/check_no_github_actions.py [--repo-dir .] [--list]
"""

from __future__ import annotations

import argparse
from pathlib import Path


def find_workflows(repo_dir: Path) -> list[Path]:
    workflows = Path(repo_dir) / ".github" / "workflows"
    if not workflows.is_dir():
        return []
    return sorted(p for p in workflows.rglob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", default=".", help="Repository root (default: .)")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List every workflow file without failing",
    )
    args = parser.parse_args()

    files = find_workflows(Path(args.repo_dir))

    if not files:
        print("OK - No GitHub Actions workflows found.")
        return 0

    if args.list:
        print(f"Found {len(files)} workflow file(s):")
        for f in files:
            print(f"  {f.as_posix()}")
        return 0

    print(f"VIOLATION - {len(files)} GitHub Actions workflow file(s) found:\n")
    for f in files:
        print(f"  {f.as_posix()}")
    print(
        "\nGitHub Actions execution is prohibited — everything (CI checks, "
        "security scans, builds, agent runs) must run on the Kubernetes "
        "cluster. Remove the workflow files and move the jobs to cluster "
        "CronJobs/Jobs."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
