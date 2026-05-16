"""
Utility functions for Secret Remover Agent.
"""
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any


def find_latest_results(log_func: Callable[..., None], results_glob: str) -> dict[str, Any] | None:
    """Return the content of the most recent security-scanner result file."""
    candidates: list[Path] = []
    env_dir = os.getenv("RESULTS_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path.cwd())
    candidates.append(Path(__file__).resolve().parents[3])

    all_files: list[Path] = []
    for base in candidates:
        try:
            pattern = str(base / results_glob)
            log_func(f"Searching for results in: {pattern}")
            all_files.extend(Path(base).glob(results_glob))
        except Exception as e:
            log_func(f"Error searching for results in {base}: {e}", "WARNING")

    if not all_files:
        return None

    for candidate in sorted({p.resolve() for p in all_files}, reverse=True):
        try:
            with open(candidate, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                log_func(f"Ignoring invalid scanner result (not a dict): {candidate}", "WARNING")
                continue
            if "repositories_with_findings" not in data:
                log_func(f"Ignoring invalid scanner result (missing key): {candidate}", "WARNING")
                continue
            return data
        except json.JSONDecodeError as exc:
            log_func(f"Ignoring malformed JSON in {candidate}: {exc}", "WARNING")
        except Exception as exc:
            log_func(f"Error reading scanner result {candidate}: {exc}", "WARNING")

    return None


def redact_context_line(line: str) -> str:
    """Mask likely secret material before sending file context to the AI."""
    redacted = line
    redacted = re.sub(
        r'(["\'])([^"\']{6,})(["\'])',
        lambda match: f"{match.group(1)}<redacted>{match.group(3)}",
        redacted,
    )
    redacted = re.sub(r'([=:]\s*)([^,\s#]+)', r'\1<redacted>', redacted)
    redacted = re.sub(r'\b[A-Za-z0-9_\-/+=]{12,}\b', '<redacted>', redacted)
    return redacted[:240]


def build_redacted_context(clone_dir: str, finding: dict[str, Any]) -> str:
    """Read a small local window around the finding and redact likely secrets."""
    file_path = finding.get("file", "")
    if not file_path:
        return "Context unavailable: missing file path."

    full_path = os.path.join(clone_dir, file_path)
    if not os.path.exists(full_path):
        return "Context unavailable: file not found in cloned repository."

    try:
        with open(full_path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except Exception as exc:
        return f"Context unavailable: {exc}"

    line_number = int(finding.get("line", 0) or 0)
    line_index = max(line_number - 1, 0)
    start = max(line_index - 2, 0)
    end = min(line_index + 3, len(lines))

    rendered = []
    for idx in range(start, end):
        marker = ">" if idx == line_index else " "
        rendered.append(
            f"{marker} {idx + 1}: {redact_context_line(lines[idx].rstrip())}"
        )
    return "\n".join(rendered)[:1000]


def get_original_line(clone_dir: str, finding: dict[str, Any]) -> str:
    """Return the raw original line from the file (not redacted), for Telegram reporting."""
    file_path = finding.get("file", "")
    if not file_path:
        return ""
    full_path = os.path.join(clone_dir, file_path)
    if not os.path.exists(full_path):
        return ""
    try:
        with open(full_path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        line_number = int(finding.get("line", 0) or 0)
        line_index = max(line_number - 1, 0)
        if 0 <= line_index < len(lines):
            return lines[line_index].rstrip()
    except Exception:
        pass
    return ""


def build_commit_url(repo_name: str, commit_sha: str) -> str:
    """Build GitHub URL to a specific commit."""
    return f"https://github.com/{repo_name}/commit/{commit_sha}"


def build_file_line_url(repo_name: str, commit_sha: str, file_path: str, line: int) -> str:
    """Build GitHub URL to a specific file+line at a given commit."""
    return f"https://github.com/{repo_name}/blob/{commit_sha}/{file_path}#L{line}"


def build_repo_url(repo_name: str) -> str:
    """Build GitHub URL to a repository."""
    return f"https://github.com/{repo_name}"

