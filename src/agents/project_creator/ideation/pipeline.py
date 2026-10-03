"""Ideation pipeline: seed -> diverge -> enrich -> critique -> specify -> quality gate."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

from .config import IdeationConfig
from .prompts import critique_prompt, diverge_prompt, specify_prompt
from .rules import CRITERIA, crowd_penalty, name_problem, parse_json, render_prompt
from .seed import Seed, Signals, pick_seed
from .similar import Searcher


class IdeationPipeline:
    def __init__(
        self,
        generate: Callable[[str], str],
        log: Callable[..., None],
        rng: random.Random | None = None,
        config: IdeationConfig | None = None,
        critic: Callable[[str], str] | None = None,
        search: Searcher | None = None,
        signals: Signals | None = None,
    ):
        self._generate, self._log, self._rng = generate, log, rng
        self._critic = critic or generate
        self._search, self._signals = search, signals or Signals()
        self._cfg = config or IdeationConfig()
        self.report: list[dict[str, Any]] = []  # one entry per attempt, for the memory log

    def run(self, history: list[str], existing_names: list[str]) -> dict[str, Any] | None:
        self.report = []
        for attempt in range(1, self._cfg.attempts + 1):
            seed = pick_seed(history, self._rng, self._signals)
            self._log(f"Ideation attempt {attempt}: {seed.domain} / {seed.archetype}")
            entry: dict[str, Any] = {"domain": seed.domain, "archetype": seed.archetype,
                                     "rejected": [], "chosen": None}
            self.report.append(entry)
            candidate = self._select(seed, history, existing_names, entry)
            spec = self._specify(candidate, seed, existing_names) if candidate else None
            if spec:
                spec["seed"] = {"domain": seed.domain, "archetype": seed.archetype}
                entry["chosen"] = spec["repository_name"]
                return spec
            if candidate:
                entry["rejected"].append({"name": candidate["repository_name"], "reason": "spec gate"})
        return None

    def _ask(self, prompt: str, fn: Callable[[str], str] | None = None) -> dict[str, Any] | None:
        try:
            return parse_json((fn or self._generate)(prompt))
        except Exception as exc:
            self._log(f"AI call failed during ideation: {exc}", "ERROR")
            return None

    def _pool(self, seed: Seed, history: list[str], existing: list[str], entry: dict) -> list[dict]:
        prompt = diverge_prompt(seed, history, self._cfg.candidates, self._signals.rejected)
        raw = (self._ask(prompt) or {}).get("candidates")
        pool = []
        for c in raw or []:
            if not isinstance(c, dict) or not c.get("repository_name"):
                continue
            banned = set(self._signals.rejected) & {c["repository_name"]}
            problem = ("previously rejected" if banned else
                       name_problem(c["repository_name"], existing, seed.domain.startswith("finance")))
            if problem:
                entry["rejected"].append({"name": c["repository_name"], "reason": problem})
            else:
                pool.append(c)
        return pool

    def _enrich(self, pool: list[dict]) -> None:
        if not self._search:
            return
        for c in pool:
            terms = c.pop("search_terms", None)
            total, similar = self._search(terms if isinstance(terms, list) else [])
            c["public_matches"], c["public_similar"] = total, similar

    def _select(self, seed: Seed, history: list[str], existing: list[str], entry: dict) -> dict | None:
        pool = self._pool(seed, history, existing, entry)
        if not pool:
            self._log("No viable candidates after name filtering", "WARNING")
            return None
        self._enrich(pool)
        scores = (self._ask(critique_prompt(pool, history), self._critic) or {}).get("scores") or []
        best, best_total = None, 0
        for s in scores:
            try:
                idx, vals = int(s["index"]), [int(s[c]) for c in CRITERIA]
                if not 0 <= idx < len(pool):
                    continue
                vals[3] = max(1, vals[3] - crowd_penalty(pool[idx].get("public_matches", 0)))
                total = sum(vals)
                if (total >= self._cfg.min_score and min(vals[:2]) >= self._cfg.min_core
                        and total > best_total):
                    best, best_total = pool[idx], total
            except (KeyError, TypeError, ValueError):
                continue
        for c in pool:
            if c is not best:
                entry["rejected"].append({"name": c["repository_name"], "reason": "low score"})
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
