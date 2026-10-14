"""Classify PR authors for the advisory review (Jules vs repository owner).

Jules PRs fix themselves, so they are never auto-fixed by us; only the owner's
own PRs get automated corrections.
"""

from __future__ import annotations

import os

JULES_LOGINS = {"google-labs-jules", "google-labs-jules[bot]", "jules da google"}


def is_jules(login: str | None) -> bool:
    return (login or "").strip().lower() in JULES_LOGINS


def default_owner() -> str:
    return os.getenv("GITHUB_OWNER", "juninmd")


def is_owner(login: str | None, owner: str | None = None) -> bool:
    return (login or "").strip().lower() == (owner or default_owner()).strip().lower()


def should_autofix(login: str | None, owner: str | None = None) -> bool:
    """Only the owner's own PRs get automated fixes; Jules fixes its own."""
    return not is_jules(login) and is_owner(login, owner)
