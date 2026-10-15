"""Runtime flags shared by the advisory PR review pipeline.

Single place for the env switches used by ``review_mixin`` (posting),
``review_flow`` (autofix) and the review gate, so "review by default, enforced,
but safe to dry-run" is configured in one module.
"""

from __future__ import annotations

import os

_FALSEY = {"0", "false", "no", "off"}


def enabled(name: str, default: bool = False) -> bool:
    """Read a boolean env flag; missing/empty falls back to ``default``."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in _FALSEY


def review_dry_run() -> bool:
    """When true, reviews run end-to-end but write nothing.

    No comment, label, commit status or autofix push is produced — used to
    homologate the review on real PRs without side effects.
    """
    return enabled("REVIEW_DRY_RUN", False)


def gate_min_severity() -> str:
    """Lowest finding severity that blocks the merge via the review gate."""
    value = (os.getenv("REVIEW_GATE_MIN_SEVERITY") or "").strip().lower()
    return value or "error"
