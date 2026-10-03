"""Tunable ideation parameters, overridable via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class IdeationConfig:
    candidates: int = 5
    attempts: int = 3
    min_score: int = 15  # sum of 4 criteria, max 20
    min_core: int = 3  # novelty and utility floor
    similar_search: bool = True
    critic_model: str | None = None
    memory_path: str = "results/ideation_memory.json"
    scaffold: bool = True

    @classmethod
    def from_env(cls) -> IdeationConfig:
        return cls(
            candidates=_int("IDEATION_CANDIDATES", 5, 2, 10),
            attempts=_int("IDEATION_ATTEMPTS", 3, 1, 6),
            min_score=_int("IDEATION_MIN_SCORE", 15, 4, 20),
            min_core=_int("IDEATION_MIN_CORE", 3, 1, 5),
            similar_search=_bool("IDEATION_SIMILAR_SEARCH", True),
            critic_model=(os.getenv("IDEATION_CRITIC_MODEL") or "").strip() or None,
            memory_path=os.getenv("IDEATION_MEMORY_PATH") or cls.memory_path,
            scaffold=_bool("IDEATION_SCAFFOLD", True),
        )
