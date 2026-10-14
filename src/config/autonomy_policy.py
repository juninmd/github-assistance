"""Per-repository autonomy policy: observe/suggest/fix/merge and merge gates.

Loaded from ``config/autonomy.json``. Unknown repositories default to
``observe`` (never write), which makes autonomous merge opt-in per repo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MODES = ("observe", "suggest", "fix", "merge")


@dataclass(frozen=True)
class RepoAutonomy:
    mode: str = "observe"
    max_attempts: int = 3
    require_evidence: bool = True
    required_checks: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()
    merge: bool = False

    def allows_merge(self) -> bool:
        return self.merge and self.mode == "merge"

    def allows_write(self) -> bool:
        return self.mode in ("fix", "merge")


def _norm_mode(value: Any) -> str:
    mode = str(value or "observe").strip().lower()
    return mode if mode in MODES else "observe"


def _norm_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(v) for v in value if str(v).strip())
    return ()


@dataclass
class AutonomyPolicy:
    path: str = "config/autonomy.json"
    _repos: dict[str, RepoAutonomy] = field(default_factory=dict)
    _default: RepoAutonomy = field(default_factory=RepoAutonomy)

    def __init__(self, path: str | None = None) -> None:
        self.path = path or "config/autonomy.json"
        self._repos = {}
        self._default = RepoAutonomy()
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        defaults = data.get("defaults", {})
        self._default = RepoAutonomy(
            mode=_norm_mode(defaults.get("mode", "observe")),
            max_attempts=int(defaults.get("max_attempts", 3) or 3),
            require_evidence=bool(defaults.get("require_evidence", True)),
            required_checks=_norm_tuple(defaults.get("required_checks")),
            allowed_paths=_norm_tuple(defaults.get("allowed_paths")),
            merge=bool(defaults.get("merge", False)),
        )
        for repo, cfg in (data.get("repositories") or {}).items():
            self._repos[repo.lower().strip()] = RepoAutonomy(
                mode=_norm_mode(cfg.get("mode", self._default.mode)),
                max_attempts=int(cfg.get("max_attempts", self._default.max_attempts) or 3),
                require_evidence=bool(
                    cfg.get("require_evidence", self._default.require_evidence)
                ),
                required_checks=_norm_tuple(
                    cfg.get("required_checks") or self._default.required_checks
                ),
                allowed_paths=_norm_tuple(
                    cfg.get("allowed_paths") or self._default.allowed_paths
                ),
                merge=bool(cfg.get("merge", self._default.merge)),
            )

    def for_repository(self, repository: str) -> RepoAutonomy:
        return self._repos.get(str(repository).lower().strip(), self._default)

    def allow_merge(self, repository: str) -> bool:
        return self.for_repository(repository).allows_merge()

    def to_dict(self) -> dict[str, Any]:
        def _encode(policy: RepoAutonomy) -> dict[str, Any]:
            return {
                "mode": policy.mode,
                "max_attempts": policy.max_attempts,
                "require_evidence": policy.require_evidence,
                "required_checks": list(policy.required_checks),
                "allowed_paths": list(policy.allowed_paths),
                "merge": policy.merge,
            }

        return {
            "defaults": _encode(self._default),
            "repositories": {r: _encode(p) for r, p in sorted(self._repos.items())},
        }
