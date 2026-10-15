"""Centralized discovery and selection for free opencode models."""

from __future__ import annotations

import os
import random
import secrets
import shutil

from src.utils.proc import run as proc_run

PREFERRED_FREE_MODEL = "opencode/deepseek-v4.1-flash-free"
DEFAULT_FALLBACK_MODEL = "opencode/big-pickle"

_models_cache: list[str] | None = None
_forced_model: str | None = None


def set_forced_model(model: str | None) -> None:
    """Override model for testing or manual forcing."""
    global _forced_model
    _forced_model = model


def reset_models_cache() -> None:
    """Reset cached models."""
    global _models_cache, _forced_model
    _models_cache = None
    _forced_model = None


def get_free_opencode_models(timeout: int = 20) -> list[str]:
    """Return free models with deepseek-v4.1-flash-free first, followed by randomized others."""
    global _models_cache
    if _models_cache is None:
        try:
            cmd = shutil.which("opencode") or "opencode"
            result = proc_run(
                [cmd, "models"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 and result.stdout:
                lines = [m.strip() for m in result.stdout.splitlines() if m.strip()]
                free = [m for m in lines if m.endswith("-free") or m == DEFAULT_FALLBACK_MODEL]
                _models_cache = free or [DEFAULT_FALLBACK_MODEL]
            else:
                _models_cache = [DEFAULT_FALLBACK_MODEL]
        except Exception:
            _models_cache = [DEFAULT_FALLBACK_MODEL]

    models = list(_models_cache)
    if PREFERRED_FREE_MODEL in models:
        others = [m for m in models if m != PREFERRED_FREE_MODEL]
        random.shuffle(others)
        return [PREFERRED_FREE_MODEL] + others
    shuffled = list(models)
    random.shuffle(shuffled)
    return shuffled


def select_free_opencode_model(attempt: int = 0) -> str:
    """Select model: env override > forced > deepseek (attempt 0) > random free model."""
    custom = os.getenv("OPENCODE_MODEL")
    if custom:
        return custom
    if _forced_model:
        return _forced_model

    models = get_free_opencode_models()
    if attempt == 0:
        return models[0] if models else DEFAULT_FALLBACK_MODEL
    first = models[0] if models else DEFAULT_FALLBACK_MODEL
    candidates = [m for m in models if m != first]
    return secrets.choice(candidates) if candidates else DEFAULT_FALLBACK_MODEL
