"""Homologation tool: score the README of each allowlisted repository.

Read-only: fetches each repo's README and prints its rubric score and the
elements it is missing. Writes nothing.

Usage:
    python scripts/readme_score.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.agents.readme_curator.scoring import DEFAULT_MIN_SCORE, score_readme  # noqa: E402
from src.config.repository_allowlist import RepositoryAllowlist  # noqa: E402
from src.config.settings import Settings  # noqa: E402
from src.github_client import GithubClient  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    client = GithubClient(settings.github_token)
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)

    repos = allowlist.list_repositories()
    print(f"Scoring READMEs for {len(repos)} repositories (min score {DEFAULT_MIN_SCORE})\n")

    below = 0
    for repo_name in repos:
        try:
            repo = client.get_repo(repo_name)
            content = repo.get_readme().decoded_content.decode("utf-8", "replace")
        except Exception as exc:  # missing README or API error
            below += 1
            print(f"  {repo_name}: MISSING/ERROR ({type(exc).__name__})")
            continue
        score = score_readme(content)
        flag = "needs work" if score.needs_work(DEFAULT_MIN_SCORE) else "ok"
        if score.needs_work(DEFAULT_MIN_SCORE):
            below += 1
        missing = ", ".join(score.missing) or "-"
        print(f"  {repo_name}: {score.score}/100 [{flag}] missing: {missing}")

    print(f"\n{below}/{len(repos)} READMEs abaixo da rubrica ({DEFAULT_MIN_SCORE}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
