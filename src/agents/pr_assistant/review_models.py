"""Candidate opencode models for the advisory review: free first, cloud/auto last.

Free opencode models cost nothing, so they are tried first; when none can produce
a usable verdict the cluster LiteLLM ``cloud/auto`` model is the fallback.
"""

from __future__ import annotations

import os

from src.utils.proc import run as proc_run

DEFAULT_CLOUD_MODEL = "litellm/cloud/auto"
DEFAULT_MAX_FREE = 3
_BIG_PICKLE = "opencode/big-pickle"

_cache: list[str] | None = None


def _max_free() -> int:
    try:
        return max(0, int(os.getenv("OPENCODE_REVIEW_MAX_FREE_MODELS", "") or DEFAULT_MAX_FREE))
    except ValueError:
        return DEFAULT_MAX_FREE


def free_opencode_models() -> list[str]:
    """Free opencode models, cheapest first; cached for the process lifetime."""
    global _cache
    if _cache is None:
        try:
            result = proc_run(
                ["opencode", "models"], capture_output=True, text=True, timeout=25
            )
            lines = [m.strip() for m in (result.stdout or "").splitlines() if m.strip()]
            free = [m for m in lines if m.endswith("-free") or m == _BIG_PICKLE]
        except Exception:
            free = []
        _cache = free or [_BIG_PICKLE]
    return list(_cache)


def cloud_model() -> str:
    return os.getenv("OPENCODE_REVIEW_MODEL", DEFAULT_CLOUD_MODEL) or DEFAULT_CLOUD_MODEL


def candidate_models() -> list[str]:
    """Free opencode models (bounded) followed by the cloud/auto fallback."""
    models = free_opencode_models()[:_max_free()]
    cloud = cloud_model()
    if cloud not in models:
        models.append(cloud)
    return models
