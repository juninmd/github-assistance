"""Content-level credential detection used as a push guard for agent PRs.

Every automated push goes through :func:`scan_clone`. The scan runs *after*
``git add -A`` and *before* the commit/push, over the whole working tree, so
whatever the LLM agent produced cannot reach GitHub while it still contains a
credential. Findings report file + rule id only — never the secret value.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.utils.secure_git import _WILDCARD, DEFAULT_ENV_DENY

_MAX_FILE_BYTES = 4 * 1024 * 1024

# Only matches commit-worthy token formats; placeholder strings such as
# ``ghp_your_token_here`` (too short: 15 chars) do not match. First element is
# the rule id reported in findings/audit messages.
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("github-pat", r"gh[pousr]_[A-Za-z0-9]{20,}"),
    ("github-fine-grained", r"github_pat_[A-Za-z0-9_]{22,}"),
    ("jules-key", r"AQ\.Ab8[A-Za-z0-9]{20,}"),
    ("openai-style", r"sk-[A-Za-z0-9]{20,}"),
    ("google-api-key", r"AIza[0-9A-Za-z_\-]{35}"),
    ("slack-token", r"xox[bapr]-[A-Za-z0-9-]{18,}"),
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # The original leak vector: a credential embedded in a github.com URL
    # (e.g. from ``git remote -v`` of a clone made with the token in it).
    ("url-embedded-github-cred", r"(?:https?|git\+https?)://[^/\s:@\[\]<>'\"]{15,}@github\.com"),
)


def known_secrets(env: dict[str, str] | None = None) -> list[str]:
    """Live credential values from the process environment worth matching exactly."""
    source = dict(env) if env is not None else dict(os.environ)
    values: list[str] = []
    for name, value in source.items():
        if name not in DEFAULT_ENV_DENY and not _WILDCARD.search(name):
            continue
        if value and len(value) >= 20 and not value.startswith("http"):
            values.append(value)
    return values


def scan_text(
    text: str,
    *,
    known: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[dict[str, str | int]]:
    """Scan one blob of text; returns findings with rule id + 1-based line."""
    findings: list[dict[str, str | int]] = []
    seen: set[tuple[str, int]] = set()

    for secret in known if known is not None else known_secrets(env):
        if secret in text:
            line_no = 0
            for i, line in enumerate(text.splitlines(), 1):
                if secret in line:
                    line_no = i
                    break
            key = ("known-secret", line_no)
            if key not in seen:
                seen.add(key)
                findings.append({"rule_id": "known-secret", "line": line_no})

    for rule_id, pattern in SECRET_PATTERNS:
        compiled = re.compile(pattern)
        for i, line in enumerate(text.splitlines(), 1):
            if compiled.search(line):
                key = (rule_id, i)
                if key not in seen:
                    seen.add(key)
                    findings.append({"rule_id": rule_id, "line": i})
    return findings


def scan_clone(
    clone_dir: str | os.PathLike[str],
    *,
    known: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[dict[str, str | int]]:
    """Scan the working tree of a clone; findings are ``{file, rule_id, line}``."""
    root = Path(clone_dir)
    if not root.is_dir():
        return []
    resolved = known if known is not None else known_secrets(env)

    findings: list[dict[str, str | int]] = []
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts or not path.is_file():
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for hit in scan_text(text, known=resolved):
            findings.append(
                {
                    "file": str(path.relative_to(root)).replace("\\", "/"),
                    "rule_id": hit["rule_id"],
                    "line": hit["line"],
                }
            )
    return findings


def redact_text(
    text: str | None,
    *,
    known: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Scrub credential-looking strings out of text (PR bodies, log lines)."""
    result = text or ""
    for secret in known if known is not None else known_secrets(env):
        result = result.replace(secret, "[REDACTED]")
    for _, pattern in SECRET_PATTERNS:
        result = re.sub(pattern, "[REDACTED]", result)
    return result
