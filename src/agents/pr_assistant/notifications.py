"""Notification utilities for PR Assistant Agent."""

import logging

_log = logging.getLogger(__name__)


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


def _notify_github(github_client, pr, body: str) -> None:
    """Safely post a GitHub comment and log failures."""
    try:
        github_client.comment_on_pr(pr, body)
    except Exception:
        _log.warning("Failed to post GitHub comment on PR #%s", pr.number)


def _notify_telegram(telegram, text: str, parse_mode: str = "HTML") -> None:
    """Safely send a Telegram notification and log failures."""
    try:
        telegram.send_message(text, parse_mode=parse_mode)
    except Exception:
        _log.warning("Failed to send Telegram notification")


def notify_conflict_resolved(github_client, telegram, pr, msg: str) -> None:
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

    _notify_github(github_client, pr, comment)
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
    _notify_telegram(telegram, "\n".join(lines_tg))


def notify_conflicts(github_client, telegram, pr, issue_comments: list | None = None) -> None:
    """Notify about unresolved merge conflicts (once only)."""
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any("⚠️ **Conflitos de Merge Detectados**" in (c.body or "") for c in comments):
            return
    except Exception:
        return
    _notify_github(
        github_client, pr,
        "⚠️ **Conflitos de Merge Detectados**\n\n"
        "Este PR tem conflitos de merge que não puderam ser resolvidos automaticamente. "
        "Por favor, resolva manualmente.",
    )

    repo_name = pr.base.repo.full_name
    url = pr.html_url
    esc = telegram.escape_html
    head_ref = getattr(pr.head, "ref", "unknown")
    base_ref = getattr(pr.base, "ref", "unknown")
    author = pr.user.login if pr.user else "unknown"

    _notify_telegram(
        telegram,
        f"🚨 <b>CONFLITO DE MERGE DETECTADO</b> 🚨\n"
        f"⚠️ <i>Atenção necessária</i>\n"
        f"──────────────────────────────\n"
        f"📁 <b>Repositório:</b> <code>{esc(repo_name)}</code>\n"
        f"🌿 <b>Branch:</b> <code>{esc(head_ref)}</code> ➔ <code>{esc(base_ref)}</code>\n"
        f'🔀 <b>PR:</b> <a href="{url}">#{pr.number}</a> — <b>{esc(pr.title)}</b>\n'
        f"👤 <b>Autor:</b> <code>{esc(author)}</code>\n"
        f"──────────────────────────────\n"
        f"❌ Os conflitos não puderam ser resolvidos de forma automatizada. Resolução manual necessária.",
    )


def notify_merge_failed(
    github_client, telegram, pr, error: str, issue_comments: list | None = None
) -> None:
    """Post a once-only GitHub comment when a merge attempt fails."""
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any("<!-- merge-failed -->" in (c.body or "") for c in comments):
            return
    except Exception:
        return
    _notify_github(
        github_client, pr,
        "<!-- merge-failed -->\n"
        "❌ **Merge falhou**\n\n"
        f"Tentei realizar o merge deste PR mas ocorreu um erro:\n\n"
        f"```\n{error}\n```\n\n"
        "Por favor, verifique as permissões do repositório ou se há proteções de branch "
        "que impedem o merge automático.",
    )

    repo_name = pr.base.repo.full_name
    url = pr.html_url
    esc = telegram.escape_html
    head_ref = getattr(pr.head, "ref", "unknown")
    base_ref = getattr(pr.base, "ref", "unknown")

    _notify_telegram(
        telegram,
        f"💥 <b>FALHA AO REALIZAR MERGE</b> 💥\n"
        f"──────────────────────────────\n"
        f"📁 <b>Repositório:</b> <code>{esc(repo_name)}</code>\n"
        f"🌿 <b>Branch:</b> <code>{esc(head_ref)}</code> ➔ <code>{esc(base_ref)}</code>\n"
        f'🔀 <b>PR:</b> <a href="{url}">#{pr.number}</a> — <b>{esc(pr.title)}</b>\n'
        f"──────────────────────────────\n"
        f"🛑 <b>Erro reportado:</b>\n"
        f"<pre>{esc(error[:400])}</pre>",
    )


def notify_pipeline_pending(
    github_client, telegram, pr, state: str, issue_comments: list | None = None
) -> None:
    """Post a once-only GitHub comment when CI is still running."""
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any("<!-- pipeline-pending -->" in (c.body or "") for c in comments):
            return
    except Exception:
        return
    _notify_github(
        github_client, pr,
        "<!-- pipeline-pending -->\n"
        "⏳ **Aguardando pipeline**\n\n"
        f"O pipeline de CI/CD está com estado `{state}`. "
        "O merge será realizado automaticamente assim que todas as verificações passarem.",
    )

    repo_name = pr.base.repo.full_name
    url = pr.html_url
    esc = telegram.escape_html
    head_ref = getattr(pr.head, "ref", "unknown")
    base_ref = getattr(pr.base, "ref", "unknown")

    _notify_telegram(
        telegram,
        f"⏳ <b>AGUARDANDO PIPELINE</b> ⏳\n"
        f"──────────────────────────────\n"
        f"📁 <b>Repositório:</b> <code>{esc(repo_name)}</code>\n"
        f"🌿 <b>Branch:</b> <code>{esc(head_ref)}</code> ➔ <code>{esc(base_ref)}</code>\n"
        f'🔀 <b>PR:</b> <a href="{url}">#{pr.number}</a> — <b>{esc(pr.title)}</b>\n'
        f"──────────────────────────────\n"
        f"⚙️ <b>Status da CI:</b> <code>{esc(state)}</code>\n"
        f"O merge ocorrerá automaticamente após a conclusão com sucesso do workflow.",
    )
