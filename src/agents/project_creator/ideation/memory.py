"""Local audit log of ideation runs: what was drawn, rejected and chosen.

Durable steering signals (domain/archetype per created repo) live on GitHub as repo topics
(see feedback.py); this file adds the rejected-candidate trail and survives only as long as
its path does, so point IDEATION_MEMORY_PATH at a persistent volume in the cluster.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_RUNS = 200


class IdeaMemory:
    def __init__(self, path: str, log: Callable[..., None] | None = None):
        self._path = Path(path)
        self._log = log or (lambda *a, **k: None)

    def _read(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def record(self, attempts: list[dict[str, Any]]) -> None:
        """Append one run (all attempts) and cap the file at MAX_RUNS runs."""
        if not attempts:
            return
        runs = self._read()
        runs.append({"at": datetime.now(UTC).isoformat(), "attempts": attempts})
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(runs[-MAX_RUNS:], indent=1, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            self._log(f"Could not write ideation memory: {exc}", "WARNING")

    def rejected_names(self, limit: int = 60) -> list[str]:
        names = [
            r["name"]
            for run in self._read() for a in run.get("attempts", []) for r in a.get("rejected", [])
            if r.get("name")
        ]
        return list(dict.fromkeys(names))[-limit:]

    def recent_choices(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Domains/archetypes of runs that produced a project, with their age in days."""
        now = now or datetime.now(UTC)
        out = []
        for run in self._read():
            try:
                age = (now - datetime.fromisoformat(run["at"])).days
            except (KeyError, ValueError):
                continue
            out += [{"domain": a["domain"], "archetype": a["archetype"], "age_days": age}
                    for a in run.get("attempts", []) if a.get("chosen")]
        return out
