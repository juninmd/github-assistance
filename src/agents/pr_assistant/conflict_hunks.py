"""Resolve merge conflicts hunk by hunk instead of sending the whole file.

Sending an entire file to the LLM for one small conflict wastes tokens and is the
main reason large files time out or get refused. Here each ``<<<<<<<``..``>>>>>>>``
block is sent with a few lines of context; the answer is spliced back only if the
untouched context came back byte-identical, so a model that rewrites unrelated
code cannot corrupt the file.
"""

from __future__ import annotations

import os
from collections.abc import Callable

START, SEP, END = "<<<<<<<", "=======", ">>>>>>>"
DEFAULT_CONTEXT_LINES = 12
DEFAULT_THRESHOLD_CHARS = 6000


def hunk_threshold() -> int:
    try:
        return int(os.getenv("CONFLICT_HUNK_THRESHOLD", "") or DEFAULT_THRESHOLD_CHARS)
    except ValueError:
        return DEFAULT_THRESHOLD_CHARS


def _find_hunks(lines: list[str]) -> list[tuple[int, int]] | None:
    """Return ``(start, end)`` line spans (inclusive), or None on malformed markers."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, line in enumerate(lines):
        if line.startswith(START):
            if start is not None:
                return None
            start = i
        elif line.startswith(END):
            if start is None:
                return None
            spans.append((start, i))
            start = None
    return None if start is not None else spans


def resolve_by_hunks(
    content: str,
    resolve_snippet: Callable[[str, str], str],
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> str | None:
    """Resolve every conflict; ``resolve_snippet(snippet, hunk)`` returns resolved snippet.

    Returns None if the markers are malformed, a hunk fails, the model altered the
    surrounding context, or markers survive.
    """
    lines = content.splitlines(keepends=True)
    spans = _find_hunks([ln.rstrip("\r\n") for ln in lines])
    if not spans:
        return None
    out: list[str] = []
    cursor = 0
    for n, (s, e) in enumerate(spans):
        prev_end = spans[n - 1][1] + 1 if n else 0
        next_start = spans[n + 1][0] if n + 1 < len(spans) else len(lines)
        pre_from = max(prev_end, s - context_lines, cursor)
        post_to = min(next_start, e + 1 + context_lines)
        pre, hunk, post = lines[pre_from:s], lines[s : e + 1], lines[e + 1 : post_to]
        snippet = "".join(pre + hunk + post)
        resolved = resolve_snippet(snippet, "".join(hunk))
        if not resolved or any(m in resolved for m in (START, SEP + "\n", END)):
            return None
        new_lines = resolved.splitlines(keepends=True)
        if len(new_lines) < len(pre) + len(post):
            return None
        if new_lines[: len(pre)] != pre:
            return None
        tail = new_lines[len(new_lines) - len(post) :] if post else []
        if post and [t.rstrip("\r\n") for t in tail] != [p.rstrip("\r\n") for p in post]:
            return None
        middle = new_lines[len(pre) : len(new_lines) - len(post)]
        out.extend(lines[cursor:pre_from])
        out.extend(pre)
        out.extend(middle)
        out.extend(post)
        cursor = post_to
    out.extend(lines[cursor:])
    return "".join(out)
