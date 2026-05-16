"""Notification utilities for PR Assistant Agent."""
from typing import Any

from src.agents.pr_assistant.pipeline import build_failure_comment, has_existing_failure_comment


def notify_conflict_resolved(github_client, telegram, pr, msg: str) -> None:
    """Post GitHub comment and Telegram notification about resolved conflicts."""
    author = f"@{pr.user.login}" if pr.user else "@contributor"
    comment = (
        f"\u2705 **Conflitos de Merge Resolvidos**\n\n"
        f"Oi {author}! Os conflitos de merge do PR **#{pr.number}** foram resolvidos automaticamente.\n\n"
        f"**Detalhes:** {msg}"
    )
    try:
        github_client.comment_on_pr(pr, comment)
    except Exception:
        pass
    try:
        repo_name = pr.base.repo.full_name
        text = telegram.escape(
            f"\u2705 Conflitos resolvidos em {repo_name} PR\\#{pr.number}\n{msg}"
        )
        telegram.send_message(text, parse_mode="MarkdownV2")
    except Exception:
        pass


def notify_conflicts(github_client, pr, issue_comments: list | None = None) -> None:
    """Notify about unresolved merge conflicts (once only)."""
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any("\u26a0\ufe0f **Conflitos de Merge Detectados**" in (c.body or "") for c in comments):
            return
        github_client.comment_on_pr(
            pr,
            "\u26a0\ufe0f **Conflitos de Merge Detectados**\n\n"
            "Este PR tem conflitos de merge que n\u00e3o puderam ser resolvidos automaticamente. "
            "Por favor, resolva manualmente.",
        )
    except Exception:
        pass


def notify_merge_failed(github_client, pr, error: str, issue_comments: list | None = None) -> None:
    """Post a once-only GitHub comment when a merge attempt fails."""
    marker = "<!-- merge-failed -->"
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any(marker in (c.body or "") for c in comments):
            return
        github_client.comment_on_pr(
            pr,
            f"{marker}\n"
            "\u274c **Merge falhou**\n\n"
            f"Tentei realizar o merge deste PR mas ocorreu um erro:\n\n"
            f"```\n{error}\n```\n\n"
            "Por favor, verifique as permiss\u00f5es do reposit\u00f3rio ou se h\u00e1 prote\u00e7\u00f5es de branch "
            "que impedem o merge autom\u00e1tico.",
        )
    except Exception:
        pass


def notify_pipeline_pending(github_client, pr, state: str, issue_comments: list | None = None) -> None:
    """Post a once-only GitHub comment when CI is still running."""
    marker = "<!-- pipeline-pending -->"
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any(marker in (c.body or "") for c in comments):
            return
        github_client.comment_on_pr(
            pr,
            f"{marker}\n"
            "\u23f3 **Aguardando pipeline**\n\n"
            f"O pipeline de CI/CD est\u00e1 com estado `{state}`. "
            "O merge ser\u00e1 realizado automaticamente assim que todas as verifica\u00e7\u00f5es passarem.",
        )
    except Exception:
        pass


def warn_pipeline_failure(results: dict[str, Any], pr, status: dict, github_client, issue_comments: list | None = None) -> None:
    """Post a once-only warning about pipeline failures; merge is NOT blocked."""
    results.setdefault("pipeline_failures", []).append({
        "action": "pipeline_failure", "pr": pr.number, "title": pr.title,
        "state": status["state"], "repository": pr.base.repo.full_name,
    })
    if has_existing_failure_comment(pr, issue_comments):
        return
    comment = build_failure_comment(pr, status.get("failed_checks", []))
    try:
        github_client.comment_on_pr(pr, comment)
    except Exception:
        pass
