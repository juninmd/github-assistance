"""Durable steering signals read from GitHub: topics tag each autonomous repo with its seed,
and merged pull requests tell us whether the idea turned into something real."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .catalog import load_catalog
from .seed import Signals

ROOT_TOPIC = "autonomous-project"
MATURITY_DAYS = 3  # younger repos have no verdict yet
MAX_REPOS = 30


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")[:45]


def topics_for(seed: dict[str, str] | None) -> list[str]:
    topics = [ROOT_TOPIC]
    if seed:
        topics += [f"domain-{slug(seed['domain'])}", f"shape-{slug(seed['archetype'])}"]
    return topics


def _decode(topics: list[str]) -> tuple[str | None, str | None]:
    cat = load_catalog()
    domains = {f"domain-{slug(d['name'])}": d["name"] for d in cat.domains}
    shapes = {f"shape-{slug(a['name'])}": a["name"] for a in cat.archetypes}
    return (next((domains[t] for t in topics if t in domains), None),
            next((shapes[t] for t in topics if t in shapes), None))


def _outcome_score(repo: Any) -> float:
    """1.0 merged PR, 0.5 open PR, 0.0 nothing delivered."""
    pulls = list(repo.get_pulls(state="all"))
    if any(p.merged_at is not None for p in pulls):
        return 1.0
    return 0.5 if any(p.state == "open" for p in pulls) else 0.0


def collect_signals(
    repos: list[Any], notice: str, log: Callable[..., None], now: datetime | None = None
) -> Signals:
    """Build outcomes/recent signals from repos carrying the autonomous-creation notice."""
    now, signals = now or datetime.now(UTC), Signals()
    mine = [r for r in repos if notice in (getattr(r, "description", None) or "")][:MAX_REPOS]
    for repo in mine:
        try:
            domain, shape = _decode(repo.get_topics())
            if not domain and not shape:
                continue
            age = (now - repo.created_at).days
            signals.recent.append({"domain": domain, "archetype": shape, "age_days": age})
            if age >= MATURITY_DAYS:
                signals.outcomes.append(
                    {"domain": domain, "archetype": shape, "score": _outcome_score(repo)}
                )
        except Exception as exc:
            log(f"Could not read outcome for {getattr(repo, 'name', '?')}: {exc}", "WARNING")
    return signals
