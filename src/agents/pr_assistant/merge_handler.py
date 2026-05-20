from __future__ import annotations

import re
from contextlib import suppress

from github.IssueComment import IssueComment
from github.PullRequest import PullRequest

from src.agents.pr_assistant.utils import is_human_comment


def try_merge(
    github_client,
    telegram,
    pr: PullRequest,
    results: dict,
    ai_client,
    issue_comments: list[IssueComment] | None = None,
) -> None:
    should_merge, reason = _evaluate_comments_with_llm(pr, ai_client, issue_comments)
    if not should_merge:
        try:
            github_client.comment_on_pr(pr, f"\u26a0\ufe0f PR encerrado.\n\nMotivo: {reason}")
            pr.edit(state="closed")
        except Exception as e:
            github_client.log(f"Failed to close PR #{pr.number}: {e}", "WARNING")
        results["skipped"].append({
            "pr": pr.number, "title": pr.title,
            "reason": f"llm_rejected: {reason}", "repository": pr.base.repo.full_name,
        })
        return

    success, msg = github_client.merge_pr(pr)
    if success:
        results["merged"].append({
            "action": "merged", "pr": pr.number, "title": pr.title,
            "repository": pr.base.repo.full_name,
        })
        telegram.send_pr_notification(pr)
    else:
        _notify_merge_failed(github_client, telegram, pr, msg, issue_comments)
        results["skipped"].append({
            "pr": pr.number, "title": pr.title,
            "reason": "merge_failed", "error": msg,
            "repository": pr.base.repo.full_name,
        })


def _evaluate_comments_with_llm(
    pr: PullRequest,
    ai_client,
    issue_comments: list[IssueComment] | None = None,
) -> tuple[bool, str]:
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        human = [c for c in comments[-10:] if _is_human_comment(c)]
        if not human:
            return True, "No human review"
        if ai_client is None:
            return True, "Comment AI disabled"
        text = "\n".join(f"@{c.user.login}: {c.body[:300]}" for c in human)
        response = ai_client.generate(
            f"Analyze PR comments:\n{text}\nReply with MERGE or REJECT. If REJECT, provide a short reason."
        )
        has_reject = bool(response and re.search(r'\bREJECT\b', response.upper()))
        return (not has_reject, response or "Empty response")
    except Exception:
        return True, "Evaluation failed"


def _is_human_comment(c: IssueComment) -> bool:
    from src.agents.pr_assistant.agent import ALLOWED_AUTHORS
    return is_human_comment(c, ALLOWED_AUTHORS)


def notify_conflicts(github_client, telegram, pr: PullRequest, issue_comments: list[IssueComment] | None = None) -> None:
    marker = "\u26a0\ufe0f **Conflitos de Merge Detectados**"
    with suppress(Exception):
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        if any(marker in (c.body or "") for c in comments):
            return
        github_client.comment_on_pr(
            pr,
            f"{marker}\n\n"
            "Este PR tem conflitos de merge que n\u00e3o puderam ser resolvidos automaticamente. "
            "Por favor, resolva manualmente.",
        )
    with suppress(Exception):
        repo_name = pr.base.repo.full_name
        url = pr.html_url
        text = (
            f"\u26a0\ufe0f <b>CONFLITO N\u00c3O RESOLVIDO</b>\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\U0001f4e6 <b>Repo:</b> <code>{telegram.escape_html(repo_name)}</code>\n"
            f"\U0001f500 <b>PR:</b> <a href=\"{url}\">#{pr.number}</a> \u2014 {telegram.escape_html(pr.title)}\n"
            f"\U0001f464 <b>Autor:</b> <code>{telegram.escape_html(pr.user.login if pr.user else 'unknown')}</code>\n"
            f"Resolu\u00e7\u00e3o manual necess\u00e1ria."
        )
        telegram.send_message(text, parse_mode="HTML")


def _notify_merge_failed(
    github_client, telegram, pr: PullRequest, error: str, issue_comments: list[IssueComment] | None = None
) -> None:
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
            f"\U0001f4e6 <b>Repo:</b> <code>{telegram.escape_html(repo_name)}</code>\n"
            f"\U0001f500 <b>PR:</b> <a href=\"{url}\">#{pr.number}</a> \u2014 {telegram.escape_html(pr.title)}\n"
            f"<pre>{telegram.escape_html(error[:300])}</pre>"
        )
        telegram.send_message(text, parse_mode="HTML")


def notify_pipeline_pending(github_client, telegram, pr: PullRequest, state: str, issue_comments: list | None = None) -> None:
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
            f"\U0001f4e6 <b>Repo:</b> <code>{telegram.escape_html(repo_name)}</code>\n"
            f"\U0001f500 <b>PR:</b> <a href=\"{url}\">#{pr.number}</a> \u2014 {telegram.escape_html(pr.title)}\n"
            f"\U0001f4ca <b>Estado:</b> <code>{telegram.escape_html(state)}</code>"
        )
        telegram.send_message(text, parse_mode="HTML")
