"""Local opencode PR review — posts findings as a comment on the PR itself."""

import shutil
import subprocess

from github.PullRequest import PullRequest

CLAWPATCH_MARKER = "<!-- clawpatch-review -->"

_REVIEW_MODEL = "opencode/big-pickle"
_REVIEW_TIMEOUT = 240
_MAX_DIFF_CHARS = 60000


def _opencode_cmd() -> str:
    return shutil.which("opencode") or "opencode"


def has_existing_review_comment(pr: PullRequest, issue_comments: list | None = None) -> bool:
    comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
    return any(CLAWPATCH_MARKER in (c.body or "") for c in comments)


def _build_pr_diff(pr: PullRequest) -> str:
    parts: list[str] = []
    for f in pr.get_files():
        patch = getattr(f, "patch", None)
        if not patch:
            continue
        parts.append(f"--- {f.filename} ---\n{patch}")
    diff = "\n\n".join(parts)
    if len(diff) > _MAX_DIFF_CHARS:
        diff = diff[:_MAX_DIFF_CHARS] + "\n\n[diff truncated]"
    return diff


def review_pr_with_clawpatch(pr: PullRequest) -> tuple[bool, str]:
    """Review the PR diff locally with opencode. Returns (success, report)."""
    diff = _build_pr_diff(pr)
    if not diff:
        return False, "No reviewable diff (binary-only or empty PR)"

    prompt = (
        "You are an expert code reviewer. Review the following pull request diff.\n"
        f"PR #{pr.number}: {pr.title}\n\n"
        "Focus on bugs, security risks, behavioral regressions, and missing tests.\n"
        "Begin your reply with exactly 'STATUS: LGTM' on the first line if no changes are "
        "required. Otherwise begin with 'STATUS: CHANGES' followed by a markdown bullet list "
        "of concrete, actionable findings, each referencing the file and the concern.\n\n"
        "Diff:\n"
        f"{diff}"
    )

    try:
        result = subprocess.run(
            [_opencode_cmd(), "run", "--model", _REVIEW_MODEL, prompt],
            capture_output=True,
            text=True,
            timeout=_REVIEW_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"opencode review failed: {type(exc).__name__}"

    if result.returncode != 0:
        return False, "opencode review failed"
    report = (result.stdout or "").strip()
    if not report:
        return False, "opencode returned no review output"
    return True, report


def build_review_comment(report: str) -> str:
    """Build the PR comment. Returns '' when no adjustments are needed."""
    if not report:
        return ""
    if report.lstrip().upper().startswith("STATUS: LGTM"):
        return ""
    body = report
    if body.lstrip().upper().startswith("STATUS: CHANGES"):
        body = body.split("\n", 1)[1].strip() if "\n" in body else ""
    if not body:
        return ""
    lines = [
        CLAWPATCH_MARKER,
        "## Revisao Automatica - opencode\n",
        body,
        "\n---",
        "🤖 **Origem Automatizada**",
        "- **Agente:** `pr_assistant`",
        f"- **Modelo:** `{_REVIEW_MODEL}`",
        "- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)",
    ]
    return "\n".join(lines)
