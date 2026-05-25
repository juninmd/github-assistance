"""Notification utilities for PR Assistant Agent."""

from src.agents.pr_assistant.merge_handler import (
    _notify_merge_failed as _notify_merge_failed_impl,
)
from src.agents.pr_assistant.merge_handler import (
    notify_conflicts,
    notify_pipeline_pending,
)


def notify_conflict_resolved(github_client: Any, telegram: Any, pr: PullRequest, msg: str) -> None:
    """Post GitHub comment and Telegram notification about resolved conflicts."""
    from contextlib import suppress

    author = f"@{pr.user.login}" if pr.user else "@contributor"
    lines = msg.splitlines()
    summary = lines[0] if lines else msg
    files = ""
    model = ""
    for line in lines[1:]:
        if line.startswith("**Files:**"):
            files = line.replace("**Files:**", "").strip()
        elif line.startswith("**Model/Provider:**"):
            model = line.replace("**Model/Provider:**", "").strip()

    comment_lines = [
        "\u2705 **Conflitos de Merge Resolvidos**\n",
        f"Oi {author}! Os conflitos de merge do PR **#{pr.number}** foram resolvidos automaticamente.\n",
        f"**Resumo:** {summary}",
    ]
    if files:
        comment_lines.append(f"**Arquivos alterados:** {files}")
    if model:
        comment_lines.append(f"**Modelo utilizado:** `{model}`")
    comment_lines.append("\n---\n\U0001f916 **Origem Automatizada**\n- **Agente:** `pr_assistant`\n- **Reposit\u00f3rio de origem:** [github-assistance](https://github.com/juninmd/github-assistance)")
    comment = "\n".join(comment_lines)

    with suppress(Exception):
        github_client.comment_on_pr(pr, comment)
    with suppress(Exception):
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        esc = telegram.escape_html
        lines_tg = [
            "\u2705 <b>CONFLITO RESOLVIDO</b>",
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
            f"\U0001f4e6 <b>Repo:</b> <code>{esc(repo_name)}</code>",
            f"\U0001f500 <b>PR:</b> <a href=\"{url}\">#{pr.number}</a> \u2014 {esc(pr.title)}",
            f"\u2139\ufe0f {esc(summary)}",
        ]
        if files:
            lines_tg.append(f"\U0001f4dd <b>Arquivos:</b> <code>{esc(files)}</code>")
        if model:
            lines_tg.append(f"\U0001f916 <b>Modelo:</b> <code>{esc(model)}</code>")
        telegram.send_message("\n".join(lines_tg), parse_mode="HTML")


def notify_merge_failed(github_client, telegram, pr, error, issue_comments=None):
    return _notify_merge_failed_impl(github_client, telegram, pr, error, issue_comments)


__all__ = [
    "notify_conflict_resolved",
    "notify_conflicts",
    "notify_merge_failed",
    "notify_pipeline_pending",
]
