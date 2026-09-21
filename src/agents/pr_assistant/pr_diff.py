"""Shared PR diff collection and review prompt, bounded for a single LLM/opencode call."""

from __future__ import annotations

from github.PullRequest import PullRequest

_MAX_DIFF_CHARS = 12000
_MAX_FILES = 30


def collect_diff(pr: PullRequest) -> str:
    parts: list[str] = []
    total = 0
    for f in list(pr.get_files())[:_MAX_FILES]:
        patch = getattr(f, "patch", None)
        if not patch:
            continue
        chunk = f"--- {f.filename} ---\n{patch}\n"
        if total + len(chunk) > _MAX_DIFF_CHARS:
            parts.append(f"--- {f.filename} --- (truncated)")
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n".join(parts)


def build_review_prompt(pr: PullRequest, diff: str) -> str:
    return (
        "You are a senior software engineer doing a pull request code review.\n"
        "Review ONLY the diff below for real defects: bugs, security issues "
        "(injection, secrets, unsafe input handling), and correctness regressions.\n"
        "Ignore style nits. Be concise. If there is nothing to flag, reply exactly: "
        "No issues found.\n"
        "Format findings as a short markdown bullet list, each bullet naming the "
        "file and the concrete problem.\n\n"
        f"PR title: {pr.title}\n\n"
        f"Diff:\n{diff}"
    )
