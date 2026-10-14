"""One-off: label every open issue in the owner's repos 'jules' and assign it to the owner.

Dry-run by default; pass --apply to write. Each new 'jules' label starts a Jules session.
Usage: uv run python scripts/backfill_jules_label.py [--apply]
"""
import argparse
import os
import sys

from dotenv import load_dotenv
from github import Auth, Github

from src.agents import utils

_ACTIVE_COLOR = "6f42c1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252; issue titles are unicode

    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 1
    owner = os.getenv("GITHUB_OWNER", "juninmd")
    label = utils.ROADMAP_ACTIVE_LABEL

    gh = Github(auth=Auth.Token(token), per_page=100)
    # Search caps at 1000 results; fail loud instead of silently skipping the rest.
    results = gh.search_issues(f"is:issue is:open user:{owner} archived:false")
    if results.totalCount >= 1000:
        print(f"{results.totalCount} issues exceed the 1000 search cap; split the query", file=sys.stderr)
        return 1

    labeled = assigned = failed = 0
    ensured: set[str] = set()
    for issue in results:
        repo = issue.repository
        needs_label = not utils.issue_has_label(issue, label)
        needs_assign = not any(a.login.lower() == owner.lower() for a in issue.assignees)
        if not (needs_label or needs_assign):
            continue
        print(f"{repo.full_name}#{issue.number} label={needs_label} assign={needs_assign} {issue.title[:60]}")
        if not args.apply:
            labeled += needs_label
            assigned += needs_assign
            continue
        try:
            if needs_label:
                if repo.full_name not in ensured:
                    utils.ensure_label(repo, label, _ACTIVE_COLOR, "Triggers a Jules session", print)
                    ensured.add(repo.full_name)
                issue.add_to_labels(label)
                labeled += 1
            if needs_assign and utils.assign_owner(issue, owner, print):
                assigned += 1
        except Exception as e:
            failed += 1
            print(f"  FAILED: {type(e).__name__}: {e}", file=sys.stderr)

    mode = "applied" if args.apply else "dry-run"
    print(f"[{mode}] scanned={results.totalCount} label={labeled} assign={assigned} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
