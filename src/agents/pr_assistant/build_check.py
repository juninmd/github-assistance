"""Build/test gate run on an auto-fix before it is pushed.

Cheap checks (``git diff --check``, ``py_compile``) catch syntax slips but not a
fix that breaks the build. This runs the project's own fast check (pytest, go
build, cargo check, npm build/test) in the clone and rejects the push when it
fails. Environment problems (tool missing, dependencies not installed) are
*skipped*, never treated as a failed fix, so the gate cannot block on infra.

Control with ``PR_FIX_VALIDATE``: ``auto`` (default) or ``off``;
``PR_FIX_VALIDATE_TIMEOUT`` bounds each command (seconds, default 300).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from src.utils.proc import run as proc_run

# Output markers meaning "the environment cannot run this", not "the fix is bad".
_ENV_MARKERS = (
    "no module named",
    "command not found",
    "modulenotfounderror",
    "cannot find module",
    "error: no such command",
    "executable file not found",
    "no tests ran",
    "error collecting",
)
_TAIL_CHARS = 600


def validation_mode() -> str:
    return "off" if os.getenv("PR_FIX_VALIDATE", "auto").lower() in {"off", "0", "false"} else "auto"


def _timeout() -> int:
    try:
        return max(30, int(os.getenv("PR_FIX_VALIDATE_TIMEOUT", "300")))
    except ValueError:
        return 300


def detect_commands(clone_dir: str) -> list[tuple[str, list[str]]]:
    """Return ``(label, argv)`` checks for the project types found in ``clone_dir``."""
    root = Path(clone_dir)
    cmds: list[tuple[str, list[str]]] = []
    if (root / "go.mod").is_file() and shutil.which("go"):
        cmds.append(("go build", ["go", "build", "./..."]))
    if (root / "Cargo.toml").is_file() and shutil.which("cargo"):
        cmds.append(("cargo check", ["cargo", "check", "--quiet"]))
    if (root / "package.json").is_file() and (root / "node_modules").is_dir() and shutil.which("npm"):
        text = (root / "package.json").read_text(encoding="utf-8", errors="replace")
        for script in ("build", "test"):
            if f'"{script}"' in text:
                cmds.append((f"npm {script}", ["npm", "run", script, "--silent"]))
                break
    if (root / "tests").is_dir() and (
        (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file()
    ):
        cmds.append(("pytest", [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"]))
    return cmds


def _env_problem(returncode: int, output: str) -> bool:
    low = output.lower()
    return returncode in (126, 127) or any(m in low for m in _ENV_MARKERS)


def _untracked(clone_dir: str) -> set[str]:
    out = proc_run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=clone_dir, capture_output=True, text=True, timeout=60,
    )
    return {line for line in (out.stdout or "").splitlines() if line}


def _remove_new_artifacts(clone_dir: str, before: set[str]) -> None:
    """Delete files the checks created so they never reach the fix commit."""
    for rel in _untracked(clone_dir) - before:
        try:
            (Path(clone_dir) / rel).unlink()
        except OSError:
            pass


def run_project_checks(clone_dir: str) -> tuple[bool, str]:
    """Run the project's build/test gate. Returns ``(ok, message)``."""
    if validation_mode() == "off":
        return True, "build gate off"
    cmds = detect_commands(clone_dir)
    if not cmds:
        return True, "build gate skipped (no runnable check)"
    before = _untracked(clone_dir)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CI": "1"}
    try:
        return _run_all(clone_dir, cmds, env)
    finally:
        _remove_new_artifacts(clone_dir, before)


def _run_all(
    clone_dir: str, cmds: list[tuple[str, list[str]]], env: dict[str, str]
) -> tuple[bool, str]:
    passed: list[str] = []
    skipped: list[str] = []
    for label, argv in cmds:
        try:
            result = proc_run(
                argv, cwd=clone_dir, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=_timeout(), env=env,
            )
        except Exception as exc:  # noqa: BLE001 - timeouts/OS errors: never block on infra
            skipped.append(f"{label} ({type(exc).__name__})")
            continue
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if result.returncode == 0:
            passed.append(label)
        elif _env_problem(result.returncode, output):
            skipped.append(f"{label} (env)")
        else:
            return False, f"{label} failed: {output[-_TAIL_CHARS:]}"
    parts = []
    if passed:
        parts.append("build gate passed: " + ", ".join(passed))
    if skipped:
        parts.append("skipped: " + ", ".join(skipped))
    return True, "; ".join(parts) or "build gate skipped"
