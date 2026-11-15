"""Optional TOML feature file layered under environment variables.

Precedence: real environment (and .env) > ``config/features.toml`` > code defaults.
The file holds non-secret toggles and tuning values under ``[env]``, keyed by the
same names the environment uses, so every existing setting is configurable
without code changes. Secrets (tokens, keys) must stay in the environment.
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_FEATURES_PATH = "config/features.toml"
SECRET_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD")


def load_features_file(path: str | None = None) -> dict[str, str]:
    """Return the ``[env]`` table as strings; missing file means no overrides."""
    file = Path(path or os.getenv("FEATURES_FILE", DEFAULT_FEATURES_PATH))
    if not file.is_file():
        return {}
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ValueError(f"Invalid features file {file}: {exc}") from exc
    table = data.get("env", {})
    if not isinstance(table, dict):
        raise ValueError(f"{file}: [env] must be a table")
    values: dict[str, str] = {}
    for name, value in table.items():
        if any(marker in name.upper() for marker in SECRET_MARKERS):
            logger.warning("features file: ignoring secret-like key %s (use the environment)", name)
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        values[name] = str(value)
    return values


def apply_features_file(path: str | None = None) -> list[str]:
    """Set file values as env defaults; real env vars win. Returns applied names."""
    applied = []
    for name, value in load_features_file(path).items():
        if name not in os.environ:
            os.environ[name] = value
            applied.append(name)
    return applied
