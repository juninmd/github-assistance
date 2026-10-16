"""Homologation tool: detect dependency ecosystems for the allowlisted repos.

Read-only: reads each repo's git tree and reports the ecosystems the
Dependency Manager would act on. Creates no branch, issue or pull request.

Usage:
    python scripts/dependency_dry_run.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.agents.dependency_manager.detect import detect_ecosystems, root_filenames  # noqa: E402
from src.config.repository_allowlist import RepositoryAllowlist  # noqa: E402
from src.config.settings import Settings  # noqa: E402
from src.github_client import GithubClient  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    client = GithubClient(settings.github_token)
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)

    repos = allowlist.list_repositories()
    print(f"Detecting dependency ecosystems for {len(repos)} allowlisted repositories\n")

    actionable = 0
    for repo_name in repos:
        try:
            repo = client.get_repo(repo_name)
            tree = repo.get_git_tree(repo.default_branch, recursive=True)
            files = [item.path for item in tree.tree]
            ecosystems = detect_ecosystems(root_filenames(files))
        except Exception as exc:
            print(f"  {repo_name}: ERROR {type(exc).__name__}: {exc}")
            continue
        if ecosystems:
            actionable += 1
            print(f"  {repo_name}: " + ", ".join(e.summary for e in ecosystems))
        else:
            print(f"  {repo_name}: no dependencies")

    print(f"\n{actionable}/{len(repos)} repositorios teriam um PR de dependencias.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
