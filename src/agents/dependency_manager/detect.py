"""Detect a repository's dependency ecosystems from its tracked files.

Pure and dependency-free so it can be unit-tested without GitHub access. The
agent uses it to decide whether a repo has dependencies worth refreshing and
which tooling (audit/outdated) to ask opencode to run.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# name, manifests, lockfiles, audit command hint, outdated command hint
_SPECS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str, str], ...] = (
    (
        "node",
        ("package.json",),
        ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"),
        "npm audit --json (ou pnpm audit / yarn audit)",
        "npm outdated (ou pnpm outdated / yarn outdated)",
    ),
    (
        "python",
        ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile"),
        ("uv.lock", "poetry.lock", "Pipfile.lock"),
        "pip-audit / osv-scanner",
        "uv pip list --outdated (ou pip list --outdated)",
    ),
    ("go", ("go.mod",), ("go.sum",), "govulncheck", "go list -u -m all"),
    ("rust", ("Cargo.toml",), ("Cargo.lock",), "cargo audit", "cargo outdated"),
    ("php", ("composer.json",), ("composer.lock",), "composer audit", "composer outdated"),
)


@dataclass(frozen=True)
class Ecosystem:
    """A detected dependency ecosystem and the tooling hints for it."""

    name: str
    manifest: str
    lockfile: str | None
    audit_hint: str
    outdated_hint: str

    @property
    def summary(self) -> str:
        lock = self.lockfile or "sem lockfile"
        return f"{self.name} ({self.manifest}, {lock})"


def root_filenames(files: Iterable[str]) -> set[str]:
    """Return the top-level file names (no path separators), lowercased."""
    return {f.lower() for f in files if f and "/" not in f.strip("/")}


def detect_ecosystems(files: Iterable[str]) -> list[Ecosystem]:
    """Detect every supported ecosystem present in the repo's file list."""
    present = root_filenames(files)
    found: list[Ecosystem] = []
    for name, manifests, lockfiles, audit, outdated in _SPECS:
        manifest = next((m for m in manifests if m.lower() in present), None)
        if manifest is None:
            continue
        lockfile = next((lk for lk in lockfiles if lk.lower() in present), None)
        found.append(
            Ecosystem(
                name=name,
                manifest=manifest,
                lockfile=lockfile,
                audit_hint=audit,
                outdated_hint=outdated,
            )
        )
    return found
