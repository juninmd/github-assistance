"""Classify PR authors for the advisory review (Jules vs repository owner).

Jules is supposed to fix its own PRs, but in practice it often does not, so its
PRs get automated corrections too (opt out with ``REVIEW_AUTOFIX_JULES=false``).
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


def autofix_jules_enabled() -> bool:
    return os.getenv("REVIEW_AUTOFIX_JULES", "true").lower() in {"1", "true", "yes", "on"}


def should_autofix(login: str | None, owner: str | None = None) -> bool:
    """Owner PRs always; Jules PRs too unless ``REVIEW_AUTOFIX_JULES`` disables it."""
    if is_owner(login, owner):
        return True
    return is_jules(login) and autofix_jules_enabled()
