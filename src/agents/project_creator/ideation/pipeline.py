"""Ideation pipeline: seed -> diverge -> critique -> specify -> quality gate."""

from __future__ import annotations

import json
import random
import re
from collections.abc import Callable
from typing import Any

from .prompts import critique_prompt, diverge_prompt, specify_prompt
from .seed import Seed, pick_seed

CRITERIA = ("novelty", "utility", "feasibility", "distinctiveness")
MIN_TOTAL = 15  # out of 20
MIN_CORE = 3  # novelty and utility must each reach this
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


class IdeationPipeline:
    def __init__(
        self,
        generate: Callable[[str], str],
        log: Callable[..., None],
        rng: random.Random | None = None,
        candidates: int = 5,
        attempts: int = 3,
    ):
        self._generate, self._log, self._rng = generate, log, rng
        self._n, self._attempts = candidates, attempts

    def run(self, history: list[str], existing_names: list[str]) -> dict[str, Any] | None:
        for attempt in range(1, self._attempts + 1):
            seed = pick_seed(history, self._rng)
            self._log(f"Ideation attempt {attempt}: {seed.domain} / {seed.archetype}")
            candidate = self._select(seed, history, existing_names)
            if not candidate:
                continue
            spec = self._specify(candidate, seed, existing_names)
            if spec:
                return spec
        return None

    def _ask(self, prompt: str) -> dict[str, Any] | None:
        try:
            return parse_json(self._generate(prompt))
        except Exception as exc:
            self._log(f"AI call failed during ideation: {exc}", "ERROR")
            return None

    def _select(self, seed: Seed, history: list[str], existing: list[str]) -> dict | None:
        allow_finance = seed.domain.startswith("finance")
        raw = (self._ask(diverge_prompt(seed, history, self._n)) or {}).get("candidates")
        pool = [
            c for c in raw or []
            if isinstance(c, dict) and c.get("repository_name")
            and not name_problem(c["repository_name"], existing, allow_finance)
        ]
        if not pool:
            self._log("No viable candidates after name filtering", "WARNING")
            return None
        scores = (self._ask(critique_prompt(pool, history)) or {}).get("scores") or []
        best, best_total = None, 0
        for s in scores:
            try:
                idx, vals = int(s["index"]), [int(s[c]) for c in CRITERIA]
                total = sum(vals)
                if (0 <= idx < len(pool) and total >= MIN_TOTAL and min(vals[:2]) >= MIN_CORE
                        and total > best_total):
                    best, best_total = pool[idx], total
            except (KeyError, TypeError, ValueError):
                continue
        if best is None:
            self._log("No candidate passed the critique threshold", "WARNING")
        return best

    def _specify(self, candidate: dict, seed: Seed, existing: list[str]) -> dict | None:
        spec = self._ask(specify_prompt(candidate, seed, seed.stacks[0]))
        if not spec:
            return None
        features, roadmap = spec.get("features"), spec.get("roadmap_features")
        valid = (
            isinstance(features, list) and len(features) >= 4
            and all(isinstance(f, dict) for f in features)
            and isinstance(roadmap, list) and len(roadmap) >= 4
            and len(str(spec.get("idea_description", ""))) >= 80
            and spec.get("repository_name") and spec.get("tech_stack")
            and not name_problem(spec["repository_name"], existing, seed.domain.startswith("finance"))
        )
        if not valid:
            self._log("Spec failed quality gate", "WARNING")
            return None
        spec["jules_prompt"] = render_prompt(spec)
        return spec
