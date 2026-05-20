"""Notification utilities for PR Assistant Agent."""
from contextlib import suppress

from github.IssueComment import IssueComment
from github.PullRequest import PullRequest


def _parse_resolution_msg(msg: str) -> tuple[str, str, str]:
    """Extract (summary, files, model) from conflict resolver message."""
    lines = msg.splitlines()
    summary = lines[0] if lines else msg
    files = ""
    model = ""
    for line in lines[1:]:
        if line.startswith("**Files:**"):
            files = line.replace("**Files:**", "").strip()
        elif line.startswith("**Model/Provider:**"):
            model = line.replace("**Model/Provider:**", "").strip()
    return summary, files, model


def notify_conflict_resolved(github_client, telegram, pr: PullRequest, msg: str) -> None:
    """Post GitHub comment and Telegram notification about resolved conflicts."""
    author = f"@{pr.user.login}" if pr.user else "@contributor"
    summary, files, model = _parse_resolution_msg(msg)

    comment_lines = [
        "\u2705 **Conflitos de Merge Resolvidos**\n",
        f"Oi {author}! Os conflitos de merge do PR **#{pr.number}** foram resolvidos automaticamente.\n",
        f"**Resumo:** {summary}",
    ]
    if files:
        comment_lines.append(f"**Arquivos alterados:** {files}")
    if model:
        comment_lines.append(f"**Modelo utilizado:** `{model}`")
    comment_lines.append("\n---\n\ud83e\udd16 **Origem Automatizada**\n- **Agente:** `pr_assistant`\n- **Reposit\u00f3rio de origem:** [github-assistance](https://github.com/juninmd/github-assistance)")
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
            f"\ud83d\udce6 <b>Repo:</b> <code>{esc(repo_name)}</code>",
            f"\ud83d\udd00 <b>PR:</b> <a href=\"{url}\">#{pr.number}</a> \u2014 {esc(pr.title)}",
            f"\u2139\ufe0f {esc(summary)}",
        ]
        if files:
            lines_tg.append(f"\ud83d\udcdd <b>Arquivos:</b> <code>{esc(files)}</code>")
        if model:
            lines_tg.append(f"\ud83e\udd16 <b>Modelo:</b> <code>{esc(model)}</code>")
        telegram.send_message("\n".join(lines_tg), parse_mode="HTML")


def notify_conflicts(github_client, telegram, pr: PullRequest, issue_comments: list[IssueComment] | None = None) -> None:
    """Notify about unresolved merge conflicts (once only)."""
    with suppress(Exception):
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any("\u26a0\ufe0f **Conflitos de Merge Detectados**" in (c.body or "") for c in comments):
            return
        github_client.comment_on_pr(
            pr,
            "\u26a0\ufe0f **Conflitos de Merge Detectados**\n\n"
            "Este PR tem conflitos de merge que n\u00e3o puderam ser resolvidos automaticamente. "
            "Por favor, resolva manualmente.",
        )
    with suppress(Exception):
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        text = (
            f"\u26a0\ufe0f <b>CONFLITO N\u00c3O RESOLVIDO</b>\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\ud83d\udce6 <b>Repo:</b> <code>{telegram.escape_html(repo_name)}</code>\n"
            f"\ud83d\udd00 <b>PR:</b> <a href=\"{url}\">#{pr.number}</a> \u2014 {telegram.escape_html(pr.title)}\n"
            f"\ud83d\udc64 <b>Autor:</b> <code>{telegram.escape_html(pr.user.login if pr.user else 'unknown')}</code>\n"
            f"Resolu\u00e7\u00e3o manual necess\u00e1ria."
        )
        telegram.send_message(text, parse_mode="HTML")


def notify_merge_failed(github_client, telegram, pr: PullRequest, error: str, issue_comments: list[IssueComment] | None = None) -> None:
    """Post a once-only GitHub comment when a merge attempt fails."""
    marker = "<!-- merge-failed -->"
    with suppress(Exception):
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
    with suppress(Exception):
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        text = (
            f"\u274c <b>MERGE FALHOU</b>\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\ud83d\udce6 <b>Repo:</b> <code>{telegram.escape_html(repo_name)}</code>\n"
            f"\ud83d\udd00 <b>PR:</b> <a href=\"{url}\">#{pr.number}</a> \u2014 {telegram.escape_html(pr.title)}\n"
            f"<pre>{telegram.escape_html(error[:300])}</pre>"
        )
        telegram.send_message(text, parse_mode="HTML")


def notify_pipeline_pending(github_client, telegram, pr: PullRequest, state: str, issue_comments: list[IssueComment] | None = None) -> None:
    """Post a once-only GitHub comment when CI is still running."""
    marker = "<!-- pipeline-pending -->"
    with suppress(Exception):
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
    with suppress(Exception):
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        text = (
            f"\u23f3 <b>PIPELINE PENDENTE</b>\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\ud83d\udce6 <b>Repo:</b> <code>{telegram.escape_html(repo_name)}</code>\n"
            f"\ud83d\udd00 <b>PR:</b> <a href=\"{url}\">#{pr.number}</a> \u2014 {telegram.escape_html(pr.title)}\n"
            f"\ud83d\udcca <b>Estado:</b> <code>{telegram.escape_html(state)}</code>"
        )
        telegram.send_message(text, parse_mode="HTML")



