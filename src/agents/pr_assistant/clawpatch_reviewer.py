"""PR review delegation to Vibe-Code opencode tasks."""

from github.PullRequest import PullRequest

from src.vibe_code_client import VibeCodeClient

CLAWPATCH_MARKER = "<!-- clawpatch-review -->"


def has_existing_review_comment(pr: PullRequest, issue_comments: list | None = None) -> bool:
    comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
    return any(CLAWPATCH_MARKER in (c.body or "") for c in comments)


def review_pr_with_clawpatch(pr: PullRequest) -> tuple[bool, str]:
    """Create a Vibe-Code task for PR review with the opencode agent."""
    repo = pr.head.repo
    if not repo:
        return False, "PR head repo not available (fork deleted?)"

    try:
        result = VibeCodeClient().create_opencode_task(
            repository=repo.full_name,
            title=f"Review PR #{pr.number}: {pr.title}",
            base_branch=pr.base.ref,
            instructions=(
                f"Review pull request #{pr.number} in {pr.base.repo.full_name}.\n"
                f"Head branch: {pr.head.ref}\n"
                f"Base branch: {pr.base.ref}\n"
                f"PR URL: {pr.html_url}\n\n"
                "Focus on bugs, security risks, behavioral regressions, and missing tests. "
                "Post review findings or create a follow-up PR only if needed."
            ),
        )
    except Exception as exc:
        return False, f"vibe-code task creation failed: {exc}"

    return True, f"Review delegated to Vibe-Code task: {result.get('task_url')}"


def build_review_comment(report: str) -> str:
    if not report:
        return ""
    lines = [
        CLAWPATCH_MARKER,
        "## Revisao Automatica - vibe-code/opencode\n",
        report,
        "\n---",
        "🤖 **Origem Automatizada**",
        "- **Agente:** `pr_assistant`",
        "- **Modelo:** `opencode`",
        "- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)",
    ]
    return "\n".join(lines)
