"""Seed selection: pick a domain/archetype/twist using history, cooldown and outcomes."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .catalog import Catalog, load_catalog

DOMAIN_COOLDOWN_DAYS = 14
ARCHETYPE_COOLDOWN_DAYS = 7


@dataclass(frozen=True)
class Seed:
    domain: str
    angles: list[str]
    archetype: str
    archetype_desc: str
    stacks: list[str]
    twist: str


@dataclass
class Signals:
    """External evidence that steers the draw (all optional)."""

    outcomes: list[dict[str, Any]] = field(default_factory=list)  # {domain, archetype, score}
    recent: list[dict[str, Any]] = field(default_factory=list)  # {domain, archetype, age_days}
    rejected: list[str] = field(default_factory=list)  # candidate names to never re-propose


def domain_saturation(history: list[str], catalog: Catalog | None = None) -> dict[str, int]:
    """Count how many existing repos (name + description) hit each domain's keywords."""
    corpus = [item.lower() for item in history]
    return {
        d["name"]: sum(1 for text in corpus if any(k in text for k in d["keywords"]))
        for d in (catalog or load_catalog()).domains
    }


def _success_multiplier(outcomes: list[dict], key: str, name: str) -> float:
    """Smoothed success rate scaled so 'no data' is 1.0 (0.4 after 3 failures, 1.6 after 3 wins)."""
    scores = [float(o.get("score", 0)) for o in outcomes if o.get(key) == name]
    return 2 * (sum(scores) + 1) / (len(scores) + 2)


def _cooldown(recent: list[dict], key: str, name: str, days: int, factor: float) -> float:
    hit = any(r.get(key) == name and r.get("age_days", 9999) < days for r in recent)
    return factor if hit else 1.0


def pick_seed(
    history: list[str],
    rng: random.Random | None = None,
    signals: Signals | None = None,
    catalog: Catalog | None = None,
) -> Seed:
    """Weighted draw: saturated, recently used or historically unsuccessful options get rarer."""
    rng = rng or random.Random()  # noqa: S311 - not security-sensitive
    catalog, signals = catalog or load_catalog(), signals or Signals()
    saturation = domain_saturation(history, catalog)
    d_weights = [
        d["weight"] / (1 + saturation[d["name"]]) ** 2
        * _success_multiplier(signals.outcomes, "domain", d["name"])
        * _cooldown(signals.recent, "domain", d["name"], DOMAIN_COOLDOWN_DAYS, 0.2)
        for d in catalog.domains
    ]
    domain = rng.choices(catalog.domains, weights=d_weights, k=1)[0]
    a_weights = [
        _success_multiplier(signals.outcomes, "archetype", a["name"])
        * _cooldown(signals.recent, "archetype", a["name"], ARCHETYPE_COOLDOWN_DAYS, 0.3)
        for a in catalog.archetypes
    ]
    archetype = rng.choices(catalog.archetypes, weights=a_weights, k=1)[0]
    return Seed(
        domain=domain["name"],
        angles=rng.sample(domain["angles"], k=min(3, len(domain["angles"]))),
        archetype=archetype["name"],
        archetype_desc=archetype["description"],
        stacks=archetype["stacks"],
        twist=rng.choice(catalog.twists),
    )
