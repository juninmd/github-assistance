"""
Utility functions for Secret Remover Agent.
"""
import glob
import json
import os
import re
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

    # Prefer the most recent file, but skip any that are malformed.
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


def create_allowlist_session(
    repo_name: str,
    findings: list[dict],
    default_branch: str,
    create_jules_session_func: Any,
    log_func: Any,
) -> dict[str, Any] | None:
    """Create a Jules session that adds .gitleaks.toml allowlist entries."""
    entry_blocks = []
    for finding in findings:
        description = f"False positive: {finding['rule_id']} in {finding['file']}"
        entry_blocks.append(
            "\n".join(
                [
                    "[[allowlist]]",
                    f"description = {json.dumps(description)}",
                    f"rules = [{json.dumps(finding['rule_id'])}]",
                    f"paths = [{json.dumps(finding['file'])}]",
                ]
            )
        )
    entries = "\n\n".join(entry_blocks)
    instructions = (
        "Add the following allowlist entries to `.gitleaks.toml` in the "
        "repository root:\n\n"
        f"{entries}\n\n"
        ".gitleaks.toml só deve ser criado em caso de real cenário de falso positivo, com justificativa! caso contrário, faça a remoção do histórico do git! Envie o conteúdo original e conteúdo censurado depois.\n\n"
        "Then commit and open a pull request titled "
        "'chore: add gitleaks allowlist entries'."
    )
    try:
        result = create_jules_session_func(
            repository=repo_name,
            instructions=instructions,
            title=f"chore: add gitleaks allowlist ({len(findings)} entries)",
            base_branch=default_branch,
        )
        return {"kind": "IGNORE", "target": f"{len(findings)} findings", "session_id": result.get("id")}
    except Exception as exc:
        log_func(f"Failed to create allowlist session for {repo_name}: {exc}", "WARNING")
        return None


def create_removal_session(
    repo_name: str,
    finding: dict,
    default_branch: str,
    create_jules_session_func: Any,
    log_func: Any,
) -> dict[str, Any] | None:
    """Create a Jules session that rewrites history to remove a secret file."""
    file_path = finding["file"]
    reason = finding.get("_reason", "No reason provided")
    redacted_context = finding.get("redacted_context", "Context unavailable.")
    instructions = (
        f"This repository has a real secret committed at `{file_path}`.\n\n"
        f"Classification reason: {reason}\n\n"
        f"Redacted local context:\n```\n{redacted_context}\n```\n\n"
        "Please:\n"
        "1. Install `git-filter-repo` if not available: `pip install git-filter-repo`\n"
        f"2. Run: `git-filter-repo --path '{file_path}' --invert-paths --force`\n"
        "3. Force-push all branches: `git push --force --all`\n"
        "4. Force-push all tags: `git push --force --tags`\n"
        f"5. Add `{file_path}` to `.gitignore` to prevent re-commit\n"
        "6. Open a pull request documenting the remediation.\n\n"
        "⚠️ Warn in the PR description that all collaborators must re-clone."
    )
    try:
        result = create_jules_session_func(
            repository=repo_name,
            instructions=instructions,
            title=f"security: remove secret from history ({os.path.basename(file_path)})",
            base_branch=default_branch,
        )
        return {"kind": "REMOVE", "target": file_path, "session_id": result.get("id")}
    except Exception as exc:
        log_func(f"Failed to create removal session for {repo_name}/{file_path}: {exc}", "WARNING")
        return None
