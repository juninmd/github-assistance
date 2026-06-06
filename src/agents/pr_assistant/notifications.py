"""Notification utilities for PR Assistant Agent."""


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


def notify_conflict_resolved(github_client, telegram, pr, msg: str) -> None:
    """Post GitHub comment and Telegram notification about resolved conflicts."""
    author = f"@{pr.user.login}" if pr.user else "@contributor"
    summary, files, model = _parse_resolution_msg(msg)

    comment_lines = [
        "✅ **Conflitos de Merge Resolvidos**\n",
        f"Oi {author}! Os conflitos de merge do PR **#{pr.number}** foram resolvidos automaticamente.\n",
        f"**Resumo:** {summary}",
    ]
    if files:
        comment_lines.append(f"**Arquivos alterados:** {files}")
    if model:
        comment_lines.append(f"**Modelo utilizado:** `{model}`")
    comment_lines.append(
        "\n---\n🤖 **Origem Automatizada**\n- **Agente:** `pr_assistant`\n- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)"
    )
    comment = "\n".join(comment_lines)

    try:
        github_client.comment_on_pr(pr, comment)
    except Exception:
        pass
    try:
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        esc = telegram.escape_html
        head_ref = pr.head.ref if hasattr(pr, "head") and hasattr(pr.head, "ref") else "unknown"
        base_ref = pr.base.ref if hasattr(pr, "base") and hasattr(pr.base, "ref") else "unknown"
        
        lines_tg = [
            "✨ <b>CONFLITO RESOLVIDO AUTOMATICAMENTE</b> ✨",
            "🛠️ <i>Agente PR Assistant</i>",
            "──────────────────────────────",
            f"📁 <b>Repositório:</b> <code>{esc(repo_name)}</code>",
            f"🌿 <b>Branch:</b> <code>{esc(head_ref)}</code> ➔ <code>{esc(base_ref)}</code>",
            f'🔀 <b>PR:</b> <a href="{url}">#{pr.number}</a> — <b>{esc(pr.title)}</b>',
            "──────────────────────────────",
            f"📝 <b>Resumo:</b> {esc(summary)}",
        ]
        if files:
            lines_tg.append(f"📂 <b>Arquivos:</b> <code>{esc(files)}</code>")
        if model:
            lines_tg.append(f"🤖 <b>Modelo:</b> <code>{esc(model)}</code>")
        telegram.send_message("\n".join(lines_tg), parse_mode="HTML")
    except Exception:
        pass


def notify_conflicts(github_client, telegram, pr, issue_comments: list | None = None) -> None:
    """Notify about unresolved merge conflicts (once only)."""
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any(
            "⚠️ **Conflitos de Merge Detectados**" in (c.body or "") for c in comments
        ):
            return
        github_client.comment_on_pr(
            pr,
            "⚠️ **Conflitos de Merge Detectados**\n\n"
            "Este PR tem conflitos de merge que não puderam ser resolvidos automaticamente. "
            "Por favor, resolva manualmente.",
        )
    except Exception:
        pass
    try:
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        esc = telegram.escape_html
        head_ref = pr.head.ref if hasattr(pr, "head") and hasattr(pr.head, "ref") else "unknown"
        base_ref = pr.base.ref if hasattr(pr, "base") and hasattr(pr.base, "ref") else "unknown"
        author = pr.user.login if pr.user else "unknown"

        text = (
            f"🚨 <b>CONFLITO DE MERGE DETECTADO</b> 🚨\n"
            f"⚠️ <i>Atenção necessária</i>\n"
            f"──────────────────────────────\n"
            f"📁 <b>Repositório:</b> <code>{esc(repo_name)}</code>\n"
            f"🌿 <b>Branch:</b> <code>{esc(head_ref)}</code> ➔ <code>{esc(base_ref)}</code>\n"
            f'🔀 <b>PR:</b> <a href="{url}">#{pr.number}</a> — <b>{esc(pr.title)}</b>\n'
            f"👤 <b>Autor:</b> <code>{esc(author)}</code>\n"
            f"──────────────────────────────\n"
            f"❌ Os conflitos não puderam ser resolvidos de forma automatizada. Resolução manual necessária."
        )
        telegram.send_message(text, parse_mode="HTML")
    except Exception:
        pass


def notify_merge_failed(
    github_client, telegram, pr, error: str, issue_comments: list | None = None
) -> None:
    """Post a once-only GitHub comment when a merge attempt fails."""
    marker = "<!-- merge-failed -->"
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any(marker in (c.body or "") for c in comments):
            return
        github_client.comment_on_pr(
            pr,
            f"{marker}\n"
            "❌ **Merge falhou**\n\n"
            f"Tentei realizar o merge deste PR mas ocorreu um erro:\n\n"
            f"```\n{error}\n```\n\n"
            "Por favor, verifique as permissões do repositório ou se há proteções de branch "
            "que impedem o merge automático.",
        )
    except Exception:
        pass
    try:
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        esc = telegram.escape_html
        head_ref = pr.head.ref if hasattr(pr, "head") and hasattr(pr.head, "ref") else "unknown"
        base_ref = pr.base.ref if hasattr(pr, "base") and hasattr(pr.base, "ref") else "unknown"

        text = (
            f"💥 <b>FALHA AO REALIZAR MERGE</b> 💥\n"
            f"──────────────────────────────\n"
            f"📁 <b>Repositório:</b> <code>{esc(repo_name)}</code>\n"
            f"🌿 <b>Branch:</b> <code>{esc(head_ref)}</code> ➔ <code>{esc(base_ref)}</code>\n"
            f'🔀 <b>PR:</b> <a href="{url}">#{pr.number}</a> — <b>{esc(pr.title)}</b>\n'
            f"──────────────────────────────\n"
            f"🛑 <b>Erro reportado:</b>\n"
            f"<pre>{esc(error[:400])}</pre>"
        )
        telegram.send_message(text, parse_mode="HTML")
    except Exception:
        pass


def notify_pipeline_pending(
    github_client, telegram, pr, state: str, issue_comments: list | None = None
) -> None:
    """Post a once-only GitHub comment when CI is still running."""
    marker = "<!-- pipeline-pending -->"
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any(marker in (c.body or "") for c in comments):
            return
        github_client.comment_on_pr(
            pr,
            f"{marker}\n"
            "⏳ **Aguardando pipeline**\n\n"
            f"O pipeline de CI/CD está com estado `{state}`. "
            "O merge será realizado automaticamente assim que todas as verificações passarem.",
        )
    except Exception:
        pass
    try:
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        esc = telegram.escape_html
        head_ref = pr.head.ref if hasattr(pr, "head") and hasattr(pr.head, "ref") else "unknown"
        base_ref = pr.base.ref if hasattr(pr, "base") and hasattr(pr.base, "ref") else "unknown"

        text = (
            f"⏳ <b>AGUARDANDO PIPELINE</b> ⏳\n"
            f"──────────────────────────────\n"
            f"📁 <b>Repositório:</b> <code>{esc(repo_name)}</code>\n"
            f"🌿 <b>Branch:</b> <code>{esc(head_ref)}</code> ➔ <code>{esc(base_ref)}</code>\n"
            f'🔀 <b>PR:</b> <a href="{url}">#{pr.number}</a> — <b>{esc(pr.title)}</b>\n'
            f"──────────────────────────────\n"
            f"⚙️ <b>Status da CI:</b> <code>{esc(state)}</code>\n"
            f"O merge ocorrerá automaticamente após a conclusão com sucesso do workflow."
        )
        telegram.send_message(text, parse_mode="HTML")
    except Exception:
        pass
