"""Utility functions for PR Assistant Agent."""
from typing import Any


def get_prs_to_process(github_client: Any, target_owner: str, pr_ref: str | None = None) -> list:
    """Get PRs to process — either a specific ref or all open PRs."""
    if pr_ref:
        try:
            repo_ref, pr_number = pr_ref.rsplit("#", 1)
            repo = github_client.get_repo(repo_ref)
            return [repo.get_pull(int(pr_number))]
        except Exception:
            return []

    query = f"is:pr is:open archived:false user:{target_owner}"
    issues = github_client.search_prs(query)
    prs = []
    for issue in issues:
        try:
            prs.append(github_client.get_pr_from_issue(issue))
        except Exception:
            pass
    return prs

def is_trusted_author(author: str, allowed_authors: list[str]) -> bool:
    """Check if the author is in the trusted list."""
    normalized = [a.lower().replace("[bot]", "") for a in allowed_authors]
    return author.lower().replace("[bot]", "") in normalized
