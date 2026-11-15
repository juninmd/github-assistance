"""Content-level credential detection used as a push guard for agent PRs.

Every automated push goes through :func:`scan_clone`. The scan runs *after*
``git add -A`` and *before* the commit/push, over the whole working tree, so
whatever the LLM agent produced cannot reach GitHub while it still contains a
credential. Findings report file + rule id only — never the secret value.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from src.utils.proc import run as proc_run
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


def gitleaks_enabled() -> bool:
    """gitleaks runs in the push guard when installed; ``PUSH_GUARD_GITLEAKS=off`` disables."""
    if os.getenv("PUSH_GUARD_GITLEAKS", "auto").lower() in {"off", "0", "false", "no"}:
        return False
    return shutil.which("gitleaks") is not None


def gitleaks_config() -> str | None:
    """Ruleset shared with the CI actions (config/gitleaks.toml); ``GITLEAKS_CONFIG`` overrides."""
    path = os.getenv("GITLEAKS_CONFIG") or str(Path(__file__).resolve().parents[2] / "config" / "gitleaks.toml")
    return path if Path(path).is_file() else None


def gitleaks_scan(clone_dir: str | os.PathLike[str]) -> list[dict[str, str | int]]:
    """Run gitleaks over the working tree. Fail-open: tool errors return no findings
    (the built-in regex layer still guards the push). Secret values are never returned."""
    root = Path(clone_dir).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        report = str(Path(tmp) / "report.json")
        config = gitleaks_config()
        cmd = ["gitleaks", "detect", "--no-git", "--source", str(root), "--redact",
               "--no-banner", "--report-format", "json", "--report-path", report]
        if config:
            cmd += ["--config", config]
        try:
            result = proc_run(
                cmd,
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode != 1 or not Path(report).is_file():
                return []  # 0 = clean; anything else = tool problem -> fail-open
            raw = json.loads(Path(report).read_text(encoding="utf-8") or "[]")
        except Exception:  # noqa: BLE001 - never block (or crash) a push on tool failure
            return []
    findings: list[dict[str, str | int]] = []
    for item in raw if isinstance(raw, list) else []:
        file = str(item.get("File", ""))
        try:
            file = str(Path(file).resolve().relative_to(root))
        except ValueError:
            pass
        findings.append(
            {
                "file": file.replace("\\", "/"),
                "rule_id": f"gitleaks:{item.get('RuleID', 'unknown')}",
                "line": int(item.get("StartLine", 0) or 0),
            }
        )
    return findings


def scan_clone(
    clone_dir: str | os.PathLike[str],
    *,
    known: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[dict[str, str | int]]:
    """Scan the working tree of a clone; findings are ``{file, rule_id, line}``.

    Combines the built-in regex layer with gitleaks (when installed), de-duplicated
    by file + line.
    """
    root = Path(clone_dir)
    if not root.is_dir():
        return []
    findings = _scan_regex(root, known, env)
    if gitleaks_enabled():
        seen = {(f["file"], f["line"]) for f in findings}
        findings += [f for f in gitleaks_scan(root) if (f["file"], f["line"]) not in seen]
    from src.utils.sast_scan import sast_scan  # lazy: only pulls tool plumbing when scanning

    seen = {(f["file"], f["line"]) for f in findings}
    findings += [f for f in sast_scan(root) if (f["file"], f["line"]) not in seen]
    return findings


def _scan_regex(
    root: Path, known: list[str] | None, env: dict[str, str] | None
) -> list[dict[str, str | int]]:
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
