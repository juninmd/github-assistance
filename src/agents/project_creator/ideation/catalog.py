"""Catalog loader: domains, archetypes and twists live in catalog.yaml (editable, no code)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).with_name("catalog.yaml")
_REQUIRED = {
    "domains": ("name", "keywords", "angles", "weight"),
    "archetypes": ("name", "description", "stacks"),
}


@dataclass(frozen=True)
class Catalog:
    domains: list[dict[str, Any]]
    archetypes: list[dict[str, Any]]
    twists: list[str]


def _validate(data: Any) -> Catalog:
    if not isinstance(data, dict):
        raise ValueError("catalog must be a mapping")
    for section, keys in _REQUIRED.items():
        items = data.get(section)
        if not isinstance(items, list) or not items:
            raise ValueError(f"catalog.{section} must be a non-empty list")
        for item in items:
            missing = [k for k in keys if k not in item]
            if missing:
                raise ValueError(f"catalog.{section} entry missing {missing}")
    twists = data.get("twists")
    if not isinstance(twists, list) or not twists:
        raise ValueError("catalog.twists must be a non-empty list")
    return Catalog(data["domains"], data["archetypes"], [str(t) for t in twists])


@lru_cache(maxsize=4)
def _load(path: str) -> Catalog:
    with open(path, encoding="utf-8") as fh:
        return _validate(yaml.safe_load(fh))


def load_catalog(path: str | None = None) -> Catalog:
    """Load the catalog from `path`, IDEATION_CATALOG_PATH, or the bundled default.

    An invalid or unreadable override falls back to the bundled catalog.
    """
    chosen = path or os.getenv("IDEATION_CATALOG_PATH")
    if chosen:
        try:
            return _load(str(chosen))
        except (OSError, ValueError, yaml.YAMLError):
            pass
    return _load(str(DEFAULT_PATH))
