"""What an opencode run actually did: skills invoked, tokens, harness version.

``opencode run --format json`` emits one JSON event per line. Skills are loaded
on demand through the ``skill`` tool (``tool_use`` event, ``input.name``), so the
list of *invoked* skills is observed, never assumed. "Available" skills are the
directories opencode auto-loads; both are reported separately and nothing is
invented when the harness gives no event.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKILL_TOOLS = {"skill", "skills"}
_version_cache: dict[str, str] = {}


@dataclass(frozen=True)
class RunTrace:
    """Observed facts of one opencode run."""

    harness: str = "opencode"
    model: str = ""
    skills_used: tuple[str, ...] = ()
    skills_available: tuple[str, ...] = ()
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    structured: bool = False  # True when JSON events were parsed (skills_used is reliable)
    tools: tuple[str, ...] = field(default_factory=tuple)


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def parse_events(stdout: str) -> tuple[str, dict]:
    """Return ``(text, facts)`` from ``--format json`` output.

    ``text`` is the joined assistant text; when no event is recognised the raw
    stdout is returned unchanged and ``facts['structured']`` is False.
    """
    texts: list[str] = []
    skills: list[str] = []
    tools: list[str] = []
    tin = tout = 0
    cost = 0.0
    structured = False
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or "type" not in event:
            continue
        part = _dict(event.get("part"))
        kind = event["type"]
        if kind == "text":
            structured = True
            texts.append(str(part.get("text") or ""))
        elif kind == "tool_use":
            structured = True
            tool = str(part.get("tool") or "")
            tools.append(tool)
            state = _dict(part.get("state"))
            inp = _dict(state.get("input"))
            name = str(inp.get("name") or "").strip()
            if tool in SKILL_TOOLS and name and name not in skills:
                skills.append(name)
        elif kind == "step_finish":
            structured = True
            tok = _dict(part.get("tokens"))
            tin += _int(tok.get("input"))
            tout += _int(tok.get("output"))
            try:
                cost += float(part.get("cost") or 0)
            except (TypeError, ValueError):
                pass
        elif kind in {"step_start", "reasoning"}:
            structured = True
    text = "\n".join(t for t in texts if t).strip() if structured else (stdout or "")
    if structured and not text:
        text = stdout
    return text, {
        "skills_used": tuple(skills), "tools": tuple(tools), "tokens_in": tin,
        "tokens_out": tout, "cost": cost, "structured": structured,
    }


def available_skills(extra_dirs: list[str] | None = None) -> tuple[str, ...]:
    """Skill names opencode can load: ``~/.config/opencode/skills`` plus repo dirs."""
    roots = [Path.home() / ".config" / "opencode" / "skills"]
    for base in extra_dirs or []:
        roots += [Path(base) / ".opencode" / "skills", Path(base) / ".agents" / "skills"]
    names: set[str] = set()
    for root in roots:
        try:
            names.update(p.name for p in root.iterdir() if (p / "SKILL.md").is_file())
        except OSError:
            continue
    return tuple(sorted(names))


def harness_version(cmd: str = "") -> str:
    """``opencode <version>`` (cached); empty string when it cannot be read."""
    cmd = cmd or shutil.which("opencode") or "opencode"
    if cmd not in _version_cache:
        try:
            out = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [cmd, "--version"], capture_output=True, text=True, timeout=15,
                env={**os.environ, "NO_COLOR": "1"},
            ).stdout.strip().splitlines()
            _version_cache[cmd] = out[-1].strip() if out else ""
        except (subprocess.SubprocessError, OSError):
            _version_cache[cmd] = ""
    return _version_cache[cmd]


def label(trace: RunTrace | None) -> str:
    """Short footer text for the harness, e.g. ``opencode 2.3.0``."""
    if trace is None:
        return ""
    return trace.harness
