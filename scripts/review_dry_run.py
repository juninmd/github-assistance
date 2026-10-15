"""Homologation tool: run the advisory PR review for one PR with NO writes.

Usage:
    python scripts/review_dry_run.py <owner/repo#number>

It clones the PR head, runs the same free-opencode / LiteLLM review used by the
PR Assistant, prints the verdict and the comment that *would* be posted, and
reports whether the ``github-assistance/review`` gate is required by branch
protection. Nothing is written: no comment, label, commit status or push.
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("REVIEW_DRY_RUN", "true")
os.environ.setdefault("REVIEW_AUTOFIX_ENABLED", "false")

from src.agents.pr_assistant.review_flow import run_review  # noqa: E402
from src.agents.pr_assistant.review_verdict import GATE_NAME, build_review_comment  # noqa: E402
from src.ai.factory import get_ai_client  # noqa: E402
from src.config.settings import Settings  # noqa: E402
from src.github_client import GithubClient  # noqa: E402


def _gate_status(repo, branch: str) -> str:
    try:
        protection = repo.get_branch(branch).get_protection()
    except Exception as exc:  # unprotected branch or insufficient permission
        return f"NOT ENFORCED ({type(exc).__name__})"
    checks = getattr(protection, "required_status_checks", None)
    contexts = list(getattr(checks, "contexts", []) or []) if checks else []
    if GATE_NAME in contexts:
        return f"ENFORCED (required check: {GATE_NAME})"
    return f"NOT ENFORCED (branch protection has no '{GATE_NAME}' check)"


def main() -> int:
    if len(sys.argv) != 2 or "#" not in sys.argv[1]:
        print("usage: python scripts/review_dry_run.py owner/repo#number")
        return 2
    repo_slug, number = sys.argv[1].rsplit("#", 1)

    settings = Settings.from_env()
    client = GithubClient(settings.github_token)
    pr = client.get_repo(repo_slug).get_pull(int(number))

    print(f"PR:   {repo_slug}#{pr.number} — {pr.title}")
    print(f"gate: {_gate_status(pr.base.repo, pr.base.ref)}")

    ai_client = get_ai_client(
        "litellm",
        model=os.getenv("LLM_REVIEW_MODEL", "cloud/auto"),
        api_key=settings.litellm_api_key,
        api_base=settings.litellm_api_base,
    )
    verdict = run_review(pr, ai_client)
    if verdict is None:
        print("RESULT: review produced no verdict (clone/opencode/LLM failed)")
        return 1

    print(
        f"\nverdict: {verdict.verdict} | model: {verdict.model} | "
        f"critical: {verdict.critical} | fixes_applied: {verdict.fixed}"
    )
    print(f"findings: {len(verdict.findings)}")
    for finding in verdict.findings:
        print(f"  - [{finding.severity}] {finding.file}:{finding.line} — {finding.issue}")
    print("\n---- comment that WOULD be posted (dry-run: nothing written) ----")
    print(build_review_comment(verdict, head_sha=getattr(pr.head, "sha", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
