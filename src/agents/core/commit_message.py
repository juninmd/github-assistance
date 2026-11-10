"""Conventional Commits messages for every commit pushed by the agents."""

from __future__ import annotations

import re

TYPES = ("feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert")
MAX_SUBJECT = 72
_SEMANTIC = re.compile(rf"^(?:{'|'.join(TYPES)})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: \S")


def is_semantic(message: str) -> bool:
    """True when the first line follows ``type(scope): subject``."""
    return bool(_SEMANTIC.match((message or "").splitlines()[0] if message else ""))


def _clean_subject(subject: str, room: int) -> str:
    text = " ".join((subject or "").split()).rstrip(".")
    text = text[:1].lower() + text[1:] if text else text
    return text[:room].rstrip() or "atualiza código"


def semantic_message(kind: str, scope: str, subject: str, body: str = "") -> str:
    """Build ``kind(scope): subject`` (+ body); unknown ``kind`` falls back to ``chore``."""
    kind = kind if kind in TYPES else "chore"
    slug = re.sub(r"[^a-z0-9._/-]+", "-", (scope or "").lower()).strip("-")
    prefix = f"{kind}({slug}): " if slug else f"{kind}: "
    head = prefix + _clean_subject(subject, MAX_SUBJECT - len(prefix))
    return f"{head}\n\n{body.strip()}" if body.strip() else head
