"""Split a big PR diff into packages of related files, one review each.

A single diff cut at 12k chars silently skips the rest of a large PR. Files are
grouped by directory (so ``a/x.py`` and ``a/test_x.py`` stay together) and
packed up to a char budget; each package is reviewed on its own and the
verdicts are merged. Per-repo rules (``.review/rules.json``) are matched by glob.
"""

from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import replace
from pathlib import Path, PurePosixPath

from src.agents.pr_assistant.review_verdict import APPROVE, REQUEST_CHANGES, ReviewVerdict

RULES_FILE = ".review/rules.json"
_MAX_RULES_CHARS = 1500


def max_packages() -> int:
    try:
        return max(1, int(os.getenv("REVIEW_MAX_PACKAGES", "") or 4))
    except ValueError:
        return 4


def split_by_file(diff: str) -> dict[str, str]:
    """``git diff`` text -> {path: that file's section}."""
    sections: dict[str, str] = {}
    current, buf = "", []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                sections[current] = "".join(buf)
            buf = [line]
            current = line.split(" b/", 1)[1].strip() if " b/" in line else ""
        else:
            buf.append(line)
    if current:
        sections[current] = "".join(buf)
    return sections


def build_packages(sections: dict[str, str], budget: int) -> list[dict[str, str]]:
    """Group files by directory, then pack groups up to ``budget`` chars."""
    groups: dict[str, dict[str, str]] = {}
    for path, text in sections.items():
        groups.setdefault(str(PurePosixPath(path).parent), {})[path] = text[:budget]
    packages: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    size = 0
    for files in groups.values():
        for path, text in files.items():
            if cur and size + len(text) > budget:
                packages.append(cur)
                cur, size = {}, 0
            cur[path] = text
            size += len(text)
    if cur:
        packages.append(cur)
    return packages


def load_rules(clone_dir: str) -> list[dict[str, str]]:
    """Rules from ``.review/rules.json``: ``[{"path": "glob", "rule": "text"}]``."""
    try:
        data = json.loads((Path(clone_dir) / RULES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rules = data.get("rules", data) if isinstance(data, dict) else data
    return [
        {"path": str(r["path"]), "rule": str(r["rule"])}
        for r in rules if isinstance(r, dict) and r.get("path") and r.get("rule")
    ] if isinstance(rules, list) else []


def rules_text(rules: list[dict[str, str]], files: list[str]) -> str:
    """Rules whose glob matches any of ``files``, bounded in size."""
    hits = [
        f"- `{r['path']}`: {r['rule']}"
        for r in rules if any(fnmatch.fnmatch(f, r["path"]) for f in files)
    ]
    if not hits:
        return ""
    return ("Regras específicas deste repositório:\n" + "\n".join(hits))[:_MAX_RULES_CHARS] + "\n"


def merge_verdicts(verdicts: list[ReviewVerdict]) -> ReviewVerdict:
    """One verdict for all packages: any REQUEST_CHANGES wins; findings concatenate."""
    first = verdicts[0]
    blocked = any(v.verdict == REQUEST_CHANGES for v in verdicts)
    summaries = [v.summary for v in verdicts if v.summary]
    return replace(
        first,
        verdict=REQUEST_CHANGES if blocked else APPROVE,
        summary=" | ".join(dict.fromkeys(summaries)),
        findings=[f for v in verdicts for f in v.findings],
        skills_used=tuple(dict.fromkeys(s for v in verdicts for s in v.skills_used)),
    )
