"""PR code review via clawpatch CLI using opencode as provider."""
import os
import subprocess
import tempfile
from pathlib import Path

from github.PullRequest import PullRequest

_CLAWPATCH_REVIEW_TIMEOUT = 300
_CLAWPATCH_MAP_TIMEOUT = 120
_CLAWPATCH_INIT_TIMEOUT = 30

CLAWPATCH_MARKER = "<!-- clawpatch-review -->"


def has_existing_review_comment(pr: PullRequest, issue_comments: list | None = None) -> bool:
    comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
    return any(CLAWPATCH_MARKER in (c.body or "") for c in comments)


def review_pr_with_clawpatch(pr: PullRequest) -> tuple[bool, str]:
    """Clone PR branch and run clawpatch review with opencode provider.

    Returns:
        (success, report_markdown)
    """
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    repo = pr.head.repo
    if not repo:
        return False, "PR head repo not available (fork deleted?)"

    head_branch = pr.head.ref
    clone_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = str(Path(tmpdir) / "repo")
        try:
            _run(["git", "clone", "--depth=50", "--branch", head_branch, clone_url, clone_dir], cwd=tmpdir, timeout=120)
        except subprocess.CalledProcessError as e:
            return False, f"Clone failed: {(e.stderr or '').strip()}"
        except subprocess.TimeoutExpired:
            return False, "Clone timed out"

        try:
            _run(["clawpatch", "init"], cwd=clone_dir, timeout=_CLAWPATCH_INIT_TIMEOUT)
            _run(["clawpatch", "map"], cwd=clone_dir, timeout=_CLAWPATCH_MAP_TIMEOUT)
            _run(
                ["clawpatch", "review", "--provider", "opencode", "--limit", "10", "--jobs", "3"],
                cwd=clone_dir,
                timeout=_CLAWPATCH_REVIEW_TIMEOUT,
            )
        except FileNotFoundError:
            return False, "clawpatch not installed"
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            if "No features" in stderr or "nothing to review" in stderr.lower():
                return True, ""
            return False, f"clawpatch error: {stderr[:500]}"
        except subprocess.TimeoutExpired:
            return False, "clawpatch review timed out"

        try:
            result = _run(
                ["clawpatch", "report", "--plain"],
                cwd=clone_dir,
                timeout=60,
                capture=True,
            )
            report = result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return False, "Could not generate clawpatch report"

    return True, report


def build_review_comment(report: str) -> str:
    if not report:
        return ""
    lines = [
        CLAWPATCH_MARKER,
        "## 🔍 Revisão Automática — clawpatch\n",
        report,
        "\n---",
        "_Revisão gerada por [clawpatch](https://github.com/openclaw/clawpatch) via `pr_assistant`._",
    ]
    return "\n".join(lines)


def _run(
    cmd: list[str],
    cwd: str,
    timeout: int,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=capture, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd,
            getattr(result, "stdout", ""),
            getattr(result, "stderr", ""),
        )
    return result
