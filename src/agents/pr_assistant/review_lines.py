"""Line validation and de-duplication of review findings (cheap "reflection").

Models often cite lines that are not in the diff. A finding whose line is not
a changed/context line of its file loses the line (kept as a file-level note)
instead of becoming a wrong inline comment; empty and duplicate findings are
dropped. Purely deterministic: no extra LLM call.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace

from src.agents.pr_assistant.review_verdict import Finding

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_FILE = re.compile(r"^\+\+\+ b/(.+)$")


def parse_patch(patch: str) -> set[int]:
    """New-side line numbers visible in one file's unified patch."""
    lines: set[int] = set()
    current = 0
    for raw in (patch or "").splitlines():
        m = _HUNK.match(raw)
        if m:
            current = int(m.group(1))
            continue
        if not current or raw.startswith("\\"):
            continue
        if raw.startswith("-"):
            continue
        lines.add(current)
        current += 1
    return lines


def parse_diff(diff: str) -> dict[str, set[int]]:
    """Map file path -> visible new-side lines for a multi-file ``git diff``."""
    result: dict[str, set[int]] = {}
    path, chunk = "", []

    def flush() -> None:
        if path:
            result.setdefault(path, set()).update(parse_patch("\n".join(chunk)))

    for raw in (diff or "").splitlines():
        m = _FILE.match(raw)
        if raw.startswith("diff --git "):
            flush()
            path, chunk = "", []
        elif m:
            path = m.group(1)
        else:
            chunk.append(raw)
    flush()
    return result


def _key(f: Finding) -> tuple[str, int, str]:
    return f.file, f.line, re.sub(r"[^a-z0-9]+", " ", f.issue.lower()).strip()


def validate_findings(
    findings: Iterable[Finding], visible: dict[str, set[int]]
) -> list[Finding]:
    """Drop empty/duplicate findings and strip lines that are not in the diff."""
    out: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()
    for f in findings:
        if not f.issue.strip():
            continue
        if f.line and f.line not in visible.get(f.file, set()):
            f = replace(f, line=0)
        key = _key(f)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def inline_comments(findings: Iterable[Finding], visible: dict[str, set[int]]) -> list[dict]:
    """GitHub review comments for findings whose line is really in the diff."""
    icons = {"error": "🔴", "warn": "🟠", "warning": "🟠", "nit": "🟡", "info": "🔵"}
    return [
        {"path": f.file, "line": f.line, "side": "RIGHT",
         "body": f"{icons.get(f.severity, '🟡')} **{f.severity}** — {f.issue}"}
        for f in findings
        if f.line and f.line in visible.get(f.file, set())
    ]


def visible_from_pr(pr) -> dict[str, set[int]]:
    """Visible new-side lines per file from the PR's file patches."""
    return {f.filename: parse_patch(getattr(f, "patch", "") or "") for f in pr.get_files()}
