"""Gitleaks scanning helpers for the Security Scanner Agent."""
import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any

from src.utils.git_utils import clone_repo_securely


def ensure_gitleaks_installed(log_fn: Callable) -> bool:
    """Check if gitleaks is installed; attempt to install it if not."""
    try:
        result = subprocess.run(
            ["gitleaks", "version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            log_fn(f"Gitleaks is installed: {result.stdout.strip()}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    log_fn("Gitleaks not found in PATH.")

    # Only attempt auto-install on Linux
    if os.name != "posix":
        log_fn("Auto-install for gitleaks is only supported on Linux. Please install it manually.", "WARNING")
        return False

    log_fn("Attempting to install gitleaks (Linux)...")
    try:
        # Note: In restricted container environments, this will likely fail
        # unless we install to a writable directory like /tmp or /app/tmp.
        # The best fix is pre-installing in the Dockerfile.
        gitleaks_url = (
            "https://github.com/gitleaks/gitleaks/releases/download/"
            "v8.18.1/gitleaks_8.18.1_linux_x64.tar.gz"
        )
        subprocess.run(
            ["wget", "-q", gitleaks_url],
            capture_output=True, text=True, timeout=60, cwd="/tmp",
        ).check_returncode()
        subprocess.run(
            ["tar", "xzf", "gitleaks_8.18.1_linux_x64.tar.gz"],
            capture_output=True, text=True, timeout=60, cwd="/tmp",
        ).check_returncode()
        subprocess.run(
            ["chmod", "+x", "gitleaks"],
            capture_output=True, text=True, timeout=60, cwd="/tmp",
        ).check_returncode()
        result = subprocess.run(
            ["cp", "gitleaks", "/tmp/gitleaks_bin"],
            capture_output=True, text=True, timeout=60, cwd="/tmp",
        )
        if result.returncode == 0:
            log_fn("Gitleaks downloaded to /tmp/gitleaks_bin")
            # We would need to update the PATH or use full path if we use this fallback
            return True
        log_fn(f"Failed to install gitleaks: {result.stderr}", "ERROR")
        return False
    except Exception as e:
        log_fn(f"Error installing gitleaks: {type(e).__name__} - {str(e)}", "ERROR")
        return False


def sanitize_findings(findings: list[dict]) -> list[dict]:
    """Return findings with only safe metadata — never expose secret values."""
    sanitized = []
    for finding in findings:
        sanitized.append({
            "rule_id": finding.get("RuleID", "unknown"),
            "description": finding.get("Description", ""),
            "file": finding.get("File", ""),
            "line": finding.get("StartLine", 0),
            "commit": finding.get("Commit", "")[:8],
            "full_commit": finding.get("Commit", ""),
            "author": finding.get("Author", ""),
            "date": finding.get("Date", ""),
            # NEVER include: Secret, Match, or any actual credential data
        })
    return sanitized


def scan_repository(
    repo_name: str,
    default_branch: str,
    log_fn: Callable,
) -> dict[str, Any]:
    """Clone *repo_name* and run gitleaks. Returns a sanitized result dict."""
    log_fn(f"Scanning repository: {repo_name}")
    result: dict[str, Any] = {
        "repository": repo_name,
        "default_branch": default_branch,
        "findings": [],
        "error": None,
        "scanned": False,
    }

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        result["error"] = "GITHUB_TOKEN not available"
        return result

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            clone_dir = os.path.join(temp_dir, "repo")

            log_fn(f"Cloning {repo_name} (full history for secret detection)...")
            clone_result = clone_repo_securely(
                repo_name, clone_dir, token=token, single_branch=True, timeout=600,
            )
            if clone_result.returncode != 0:
                result["error"] = f"Clone failed with exit code {clone_result.returncode}"
                return result

            report_file = os.path.join(temp_dir, "gitleaks-report.json")
            log_fn(f"Running gitleaks scan on {repo_name}...")
            gitleaks_result = subprocess.run(
                [
                    "gitleaks", "detect",
                    "--source", clone_dir,
                    "--report-path", report_file,
                    "--report-format", "json",
                ],
                capture_output=True, text=True, timeout=300,
            )
            if gitleaks_result.returncode not in (0, 1):
                result["error"] = f"Gitleaks scan failed with exit code {gitleaks_result.returncode}"
                return result

            if os.path.exists(report_file):
                with open(report_file) as f:
                    try:
                        findings = json.load(f)
                        _strip_clone_prefix(findings, clone_dir)
                        result["findings"] = sanitize_findings(findings)
                    except json.JSONDecodeError as e:
                        result["error"] = f"Failed to parse gitleaks report: {e}"
                        return result

            result["scanned"] = True
            log_fn(f"Scan completed for {repo_name}: {len(result['findings'])} findings")
        except subprocess.TimeoutExpired:
            result["error"] = "Scan timeout exceeded"
        except FileNotFoundError:
            result["error"] = "Executable not found (gitleaks or git)"
        except Exception as e:
            result["error"] = f"Scan error: {str(e)}"
            log_fn(f"Error scanning {repo_name}: {e}", "ERROR")

    return result


def _strip_clone_prefix(findings: list[dict], clone_dir: str) -> None:
    """Mutate each finding's File to be relative to clone_dir."""
    norm_clone = os.path.normpath(clone_dir)
    for finding in findings:
        if "File" in finding:
            norm_file = os.path.normpath(finding["File"])
            if norm_file.startswith(norm_clone):
                finding["File"] = os.path.relpath(norm_file, start=norm_clone)
