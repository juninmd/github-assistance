"""Pure helpers: JSON parsing, name checks, crowding penalty and spec rendering."""

from __future__ import annotations

import json
import re
from typing import Any

CRITERIA = ("novelty", "utility", "feasibility", "distinctiveness")
_BANNED = {"expense", "expenses", "budget", "finance", "finances", "financial", "money",
           "wallet", "todo", "weather"}
_FILLER = {"smart", "ai", "app", "tool", "tools", "manager", "tracker", "helper", "assistant",
           "dashboard", "my", "pro", "hub", "simple", "easy", "super"}


def parse_json(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t}


def name_problem(name: str, existing: list[str], allow_finance: bool) -> str | None:
    tokens = _tokens(name)
    if not tokens or tokens <= _FILLER:
        return "name is generic"
    if not allow_finance and tokens & _BANNED:
        return "name uses a banned generic theme"
    for other in existing:
        theirs = _tokens(other)
        if theirs and len(tokens & theirs) / len(tokens | theirs) >= 0.6:
            return f"name too similar to existing repo {other}"
    return None


def crowd_penalty(public_matches: int) -> int:
    """Points subtracted from 'distinctiveness' when many public repos match the idea."""
    if public_matches >= 100:
        return 2
    return 1 if public_matches >= 20 else 0


def render_prompt(spec: dict[str, Any]) -> str:
    """Render the structured spec as the implementation brief handed to Jules."""
    features = "\n".join(
        f"{i}. **{f.get('name')}** — {f.get('description')}\n   - Acceptance: {f.get('acceptance')}"
        for i, f in enumerate(spec["features"], 1)
    )
    return (
        f"### Problem\n{spec.get('problem', '')}\n\n### Target user\n{spec.get('target_user', '')}\n\n"
        f"### Features (all required for v1)\n{features}\n\n"
        f"### Architecture\n{spec.get('architecture', '')}\n\n"
        f"### Interfaces\n{spec.get('interfaces', '')}\n\n"
        f"### Fixtures & demo\n{spec.get('fixtures', '')}\n\n"
        f"### Test plan (write these tests)\n{spec.get('test_plan', '')}\n\n"
        "Build everything on `master`, run the tests and linters until green, then open a PR."
    )
