"""How far a PR head lags its base branch.

A failing check on a stale branch is often GitHub validating a *stale merge
commit* (the PR head merged into an old base). That drift lives in the merge
result, not in the PR's files, so no source edit can fix it: the branch has to
be updated from base first, exactly like a human rebasing it.
"""

from __future__ import annotations


def commits_behind(pr) -> int:
    """Return how many commits ``pr.head`` is behind ``pr.base`` (0 when unknown)."""
    try:
        comparison = pr.base.repo.compare(pr.base.ref, pr.head.ref)
        behind = getattr(comparison, "behind_by", 0)
    except Exception:  # noqa: BLE001 - staleness detection is best-effort
        return 0
    if not isinstance(behind, int) or isinstance(behind, bool):
        return 0
    return max(0, behind)
