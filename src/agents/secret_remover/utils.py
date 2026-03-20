"""
Utility functions for Secret Remover Agent.
"""
import glob
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


def find_latest_results(log_func: Any, results_glob: str) -> dict[str, Any] | None:
    """Return the content of the most recent security-scanner result file."""
    candidates = []
    env_dir = os.getenv("RESULTS_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path.cwd())
    # Project root is assumed to be 3 levels above this file (src/agents/<agent>/utils.py)
    candidates.append(Path(__file__).resolve().parents[3])

    all_files = []
    for base in candidates:
        try:
            pattern = str(base / results_glob)
            log_func(f"Searching for results in: {pattern}")
            all_files.extend(glob.glob(pattern))
        except Exception as e:
            log_func(f"Error searching for results in {base}: {e}", "WARNING")

    if not all_files:
        return None

    for candidate in sorted(set(all_files), reverse=True):
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


def apply_allowlist_locally(
    repo_name: str,
    findings: list[dict],
    clone_dir: str,
    token: str,
    log_func: Any,
    default_branch: str = "main",
) -> bool:
    """Write .gitleaks.toml allowlist entries and commit+push directly."""
    toml_path = os.path.join(clone_dir, ".gitleaks.toml")
    existing = ""
    if os.path.exists(toml_path):
        with open(toml_path, encoding="utf-8") as f:
            existing = f.read()

    entry_blocks = []
    for finding in findings:
        description = f"False positive: {finding['rule_id']} in {finding['file']}"
        entry_blocks.append(
            "\n".join([
                "[[allowlist]]",
                f"description = {json.dumps(description)}",
                f"rules = [{json.dumps(finding['rule_id'])}]",
                f"paths = [{json.dumps(finding['file'])}]",
            ])
        )

    new_entries = "\n\n".join(entry_blocks)
    updated_content = (existing.rstrip() + "\n\n" + new_entries).strip() + "\n"

    try:
        with open(toml_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

        subprocess.run(
            ["git", "config", "user.email", "secret-remover@github-assistance"],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Secret Remover Agent"],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "add", ".gitleaks.toml"],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"chore: add gitleaks allowlist ({len(findings)} entries)"],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "push", "origin", default_branch],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        log_func(f"Allowlist applied locally for {repo_name} ({len(findings)} entries)")
        return True
    except subprocess.CalledProcessError as exc:
        log_func(f"Failed to apply allowlist for {repo_name}: {exc.stderr}", "WARNING")
        return False


def _get_remote_url(clone_dir: str) -> str:
    """Read the current origin remote URL before git-filter-repo strips it."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=clone_dir, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass
    return ""


def remove_secret_from_history(
    repo_name: str,
    finding: dict,
    clone_dir: str,
    log_func: Any,
) -> bool:
    """Run git-filter-repo to purge a file from git history and force-push."""
    file_path = finding.get("file", "")
    if not file_path:
        log_func(f"Cannot remove secret: missing file path for {repo_name}", "ERROR")
        return False

    remote_url = _get_remote_url(clone_dir)
    if not remote_url:
        log_func(f"Cannot remove secret: no remote URL for {repo_name}", "ERROR")
        return False

    try:
        result = subprocess.run(
            ["git-filter-repo", "--path", file_path, "--invert-paths", "--force"],
            cwd=clone_dir, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            log_func(
                f"git-filter-repo failed for {repo_name}/{file_path}: {result.stderr.strip()}",
                "ERROR",
            )
            return False

        # git-filter-repo strips the remote; re-add it for push
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=clone_dir, check=True, capture_output=True, text=True, timeout=10,
        )

        subprocess.run(
            ["git", "push", "--force", "--all"],
            cwd=clone_dir, check=True, capture_output=True, text=True, timeout=120,
        )
        subprocess.run(
            ["git", "push", "--force", "--tags"],
            cwd=clone_dir, capture_output=True, text=True, timeout=120,
        )
        log_func(f"Secret removed from history: {repo_name}/{file_path}")
        return True
    except subprocess.TimeoutExpired:
        log_func(f"Timeout removing secret from {repo_name}/{file_path}", "ERROR")
        return False
    except subprocess.CalledProcessError as exc:
        log_func(f"Error removing secret from {repo_name}/{file_path}: {exc.stderr}", "ERROR")
        return False
