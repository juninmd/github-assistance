"""CLI: `pr-insight explain/history` — queryable view over PR merge decisions."""

from __future__ import annotations

import argparse
import json
import sys

from src.config.settings import Settings
from src.insight.explain import explain_pr, job_history


def main() -> None:
    parser = argparse.ArgumentParser(prog="pr-insight", description="PR merge-decision insight")
    sub = parser.add_subparsers(dest="command", required=True)

    explain = sub.add_parser("explain", help="explain why a PR was not merged")
    explain.add_argument("--pr", required=True, help="owner/repo#number")
    explain.add_argument("--json", action="store_true", help="raw JSON output")

    history = sub.add_parser("history", help="durable job history for a PR")
    history.add_argument("--pr", help="owner/repo#number")
    history.add_argument("--limit", type=int, default=50)
    history.add_argument("--json", action="store_true", help="raw JSON output")

    args = parser.parse_args()
    settings = Settings.from_env()
    if args.command == "explain":
        result = explain_pr(settings, args.pr)
        _emit(result, args.json)
    else:
        rows = job_history(settings, args.pr, args.limit)
        if args.json:
            print(json.dumps({"history": rows}, indent=2))
            return
        for row in rows:
            print(
                f"{row['created_at']:.0f} {row['status']:<9} attempts={row['attempts']} "
                f"decision={row['decision'] or '-'} next={row['next_action'] or '-'} {row['key']}"
            )


def _emit(result: dict, raw_json: bool) -> None:
    if raw_json:
        print(json.dumps(result, indent=2, default=str))
        return
    print(f"PR: {result.get('pr_ref')}  state={result.get('state')} merged={result.get('merged')}")
    print(f"autonomy={result.get('autonomy_mode')} pipeline={result.get('pipeline_state')}")
    print("reasons:")
    for reason in result.get("reasons", []):
        print(f"  - {reason}")


if __name__ == "__main__":
    sys.exit(main())
