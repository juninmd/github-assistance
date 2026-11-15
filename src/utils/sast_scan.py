"""trufflehog / trivy / semgrep as extra push-guard layers for agent edits.

Ported from the ``sast`` action of ``juninmd/base-actions``. Each tool runs only
when its binary is installed, only the findings that touch the files the fix
changed can block a push (pre-existing debt in the repo is not the fix's fault),
and every error/timeout is fail-open: the regex + gitleaks layers still guard.
Findings carry tool, rule, file and line — never the matched secret text.

Env: ``PUSH_GUARD_SAST`` = ``auto`` (default, every installed tool) | ``off`` |
comma list (``semgrep,trivy``); ``PUSH_GUARD_SEMGREP_CONFIG`` (default
``p/security-audit``); ``PUSH_GUARD_TRIVY_SCANNERS`` (default ``secret,misconfig``,
no vulnerability DB download); ``PUSH_GUARD_TRUFFLEHOG_VERIFY=true`` lets trufflehog
verify credentials live against the provider (off by default: nothing leaves the box).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from src.utils.proc import run as proc_run

TOOLS = ("trufflehog", "trivy", "semgrep")
_BLOCKING_SEVERITIES = {"HIGH", "CRITICAL", "ERROR"}
_TIMEOUT = 240

Finding = dict[str, str | int]


def selected_tools() -> list[str]:
    mode = os.getenv("PUSH_GUARD_SAST", "auto").strip().lower()
    if mode in {"off", "0", "false", "no"}:
        return []
    wanted = list(TOOLS) if mode in {"auto", ""} else [t.strip() for t in mode.split(",")]
    return [t for t in wanted if t in TOOLS and shutil.which(t)]


def changed_files(root: Path) -> set[str] | None:
    """Files modified/added in the working tree; None when ``root`` is not a git repo."""
    try:
        out = proc_run(
            ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
    except Exception:  # noqa: BLE001
        return None
    if out.returncode != 0:
        return None
    files: set[str] = set()
    for entry in (out.stdout or "").split("\0"):
        if len(entry) > 3:
            files.add(entry[3:].strip())
    return files


def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


# -- parsers: tool JSON -> findings ------------------------------------------
def parse_trufflehog(raw: str, root: Path) -> list[Finding]:
    out: list[Finding] = []
    for line in raw.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        fs = ((d.get("SourceMetadata") or {}).get("Data") or {}).get("Filesystem") or {}
        if "DetectorName" in d and fs.get("file"):
            out.append({"file": _rel(fs["file"], root), "line": int(fs.get("line") or 0),
                        "rule_id": f"trufflehog:{d['DetectorName']}"})
    return out


def parse_trivy(raw: str, root: Path) -> list[Finding]:
    out: list[Finding] = []
    for res in (json.loads(raw).get("Results") or []):
        target = _rel(str(res.get("Target", "")), root)
        for s in res.get("Secrets") or []:
            out.append({"file": target, "line": int(s.get("StartLine") or 0),
                        "rule_id": f"trivy:{s.get('RuleID', 'secret')}"})
        for key, ident in (("Misconfigurations", "ID"), ("Vulnerabilities", "VulnerabilityID")):
            for m in res.get(key) or []:
                if str(m.get("Severity", "")).upper() in _BLOCKING_SEVERITIES:
                    line = int((m.get("CauseMetadata") or {}).get("StartLine") or 0)
                    out.append({"file": target, "line": line, "rule_id": f"trivy:{m.get(ident, key)}"})
    return out


def parse_semgrep(raw: str, root: Path) -> list[Finding]:
    return [
        {"file": _rel(str(r.get("path", "")), root), "line": int((r.get("start") or {}).get("line") or 0),
         "rule_id": f"semgrep:{r.get('check_id', 'rule')}"}
        for r in json.loads(raw).get("results") or []
        if str((r.get("extra") or {}).get("severity", "")).upper() in _BLOCKING_SEVERITIES
    ]


# -- command builders ------------------------------------------------------------
def _cmd_trufflehog(root: Path, targets: list[str], report: str) -> list[str]:
    verify = os.getenv("PUSH_GUARD_TRUFFLEHOG_VERIFY", "").lower() in {"1", "true", "yes"}
    cmd = ["trufflehog", "filesystem", *(targets or [str(root)]), "--json", "--no-update"]
    return cmd + ([] if verify else ["--no-verification"])


def _cmd_trivy(root: Path, targets: list[str], report: str) -> list[str]:
    scanners = os.getenv("PUSH_GUARD_TRIVY_SCANNERS", "secret,misconfig")
    return ["trivy", "fs", str(root), "--scanners", scanners, "--format", "json",
            "--output", report, "--quiet"]


def _cmd_semgrep(root: Path, targets: list[str], report: str) -> list[str]:
    config = os.getenv("PUSH_GUARD_SEMGREP_CONFIG", "p/security-audit")
    return ["semgrep", "scan", "--config", config, "--json", "--quiet", "--metrics=off",
            "--output", report, *(targets or [str(root)])]


_RUNNERS: dict[str, tuple[Callable[..., list[str]], Callable[[str, Path], list[Finding]], bool]] = {
    # name: (command builder, parser, reads stdout instead of the report file)
    "trufflehog": (_cmd_trufflehog, parse_trufflehog, True),
    "trivy": (_cmd_trivy, parse_trivy, False),
    "semgrep": (_cmd_semgrep, parse_semgrep, False),
}


def run_tool(name: str, root: Path, targets: list[str]) -> list[Finding]:
    """Run one tool; any failure returns no findings (fail-open)."""
    build, parse, use_stdout = _RUNNERS[name]
    with tempfile.TemporaryDirectory() as tmp:
        report = str(Path(tmp) / "report.json")
        try:
            res = proc_run(build(root, targets, report), cwd=str(root), capture_output=True,
                           text=True, timeout=_TIMEOUT)
            if res.returncode not in (0, 1):
                return []
            raw = res.stdout if use_stdout else Path(report).read_text(encoding="utf-8")
            return parse(raw, root) if raw.strip() else []
        except Exception:  # noqa: BLE001 - never block (or crash) a push on tool failure
            return []


def sast_scan(clone_dir: str | os.PathLike[str]) -> list[Finding]:
    """Findings from the enabled tools that fall in files changed by the fix."""
    root = Path(clone_dir).resolve()
    tools = selected_tools()
    if not tools:
        return []
    changed = changed_files(root)
    targets = sorted(f for f in (changed or set()) if (root / f).is_file())
    if changed is not None and not targets:
        return []
    found: list[Finding] = []
    for name in tools:
        found += run_tool(name, root, targets if name in {"semgrep", "trufflehog"} else [])
    if changed is not None:
        found = [f for f in found if f["file"] in changed]
    return found
