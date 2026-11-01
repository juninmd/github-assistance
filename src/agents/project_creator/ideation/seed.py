"""Seed selection: pick a domain/archetype/twist while avoiding saturated areas."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from .catalog import ARCHETYPES, DOMAINS, TWISTS
from .portfolio import Portfolio


@dataclass(frozen=True)
class Seed:
    domain: str
    angles: list[str]
    archetype: str
    archetype_desc: str
    stacks: list[str]
    twist: str


def domain_saturation(history: list[str]) -> dict[str, int]:
    """Count how many existing repos (name + description) hit each domain's keywords."""
    corpus = [item.lower() for item in history]
    return {
        d["name"]: sum(1 for text in corpus if any(k in text for k in d["kw"]))
        for d in DOMAINS
    }


def prefer_stacks(stacks: list[str], languages: list[str]) -> list[str]:
    """Stable sort: stacks written in a language the owner actually uses come first."""
    owned = {lang.lower() for lang in languages}
    if "javascript" in owned:
        owned |= {"js", "node", "nodejs"}  # stacks are written "Node.js + TypeScript", not "JavaScript"

    def uses_owned(stack: str) -> bool:
        return bool(owned & set(re.split(r"[^a-z0-9]+", stack.lower())))

    return sorted(stacks, key=lambda s: not uses_owned(s))


def pick_seed(
    history: list[str], rng: random.Random | None = None, portfolio: Portfolio | None = None
) -> Seed:
    """Weighted draw: domains already well represented in `history` become unlikely."""
    rng = rng or random.Random()  # noqa: S311 - not security-sensitive
    saturation = domain_saturation(history)
    weights = [d["weight"] / (1 + saturation[d["name"]]) ** 2 for d in DOMAINS]
    domain = rng.choices(DOMAINS, weights=weights, k=1)[0]
    archetype = rng.choice(ARCHETYPES)
    return Seed(
        domain=domain["name"],
        angles=rng.sample(domain["angles"], k=min(3, len(domain["angles"]))),
        archetype=archetype["name"],
        archetype_desc=archetype["desc"],
        stacks=prefer_stacks(archetype["stacks"], portfolio.languages if portfolio else []),
        twist=rng.choice(TWISTS),
    )
