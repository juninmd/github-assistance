"""Configurable job prioritization by impact/recurrence/effort.

The queue orders due jobs by ``priority DESC``. A JSON file
(``config/priorities.json``) maps repository patterns and PR title/label
patterns to a base priority plus bonus points, so high-impact/recurrent/low-
effort work drains first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class Priorities:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or "config/priorities.json"
        self._repo_rules: list[tuple[str, int]] = []
        self._label_rules: list[tuple[str, int]] = []
        self._title_rules: list[tuple[str, int]] = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for rule in data.get("repositories", []):
            pattern = rule.get("pattern", "")
            self._repo_rules.append((pattern, int(rule.get("priority", 0))))
        for rule in data.get("labels", []):
            self._label_rules.append((rule.get("pattern", ""), int(rule.get("priority", 0))))
        for rule in data.get("titles", []):
            self._title_rules.append((rule.get("pattern", ""), int(rule.get("priority", 0))))

    def priority_for(
        self, pr_ref: str, *, labels: list[str] | None = None, title: str = ""
    ) -> int:
        priority = 0
        repo = pr_ref.split("#", 1)[0]
        for pattern, value in self._repo_rules:
            if re.search(pattern, repo):
                priority += value
        for label in labels or []:
            for pattern, value in self._label_rules:
                if re.search(pattern, label):
                    priority += value
        for pattern, value in self._title_rules:
            if re.search(pattern, title):
                priority += value
        return priority

    @classmethod
    def default(cls) -> Priorities:
        return cls("config/priorities.json")

    def _as_dict(self) -> dict[str, Any]:
        return {
            "repositories": [
                {"pattern": p, "priority": v} for p, v in self._repo_rules
            ],
            "labels": [{"pattern": p, "priority": v} for p, v in self._label_rules],
            "titles": [{"pattern": p, "priority": v} for p, v in self._title_rules],
        }
