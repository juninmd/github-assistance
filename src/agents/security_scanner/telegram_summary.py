"""Telegram notification helpers for the Security Scanner Agent."""
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from src.notifications.telegram import TelegramNotifier

_MAX_LEN = 3800


def _send_lines(lines: list[str], telegram: TelegramNotifier) -> None:
    """Chunk *lines* into ≤ _MAX_LEN messages and send each via Telegram."""
    current = ""
    for ln in lines:
        if len(ln) > _MAX_LEN:
            ln = telegram._truncate(ln)
        if current and len(current) + len(ln) + 1 > _MAX_LEN:
            telegram.send_message(current, parse_mode="MarkdownV2")
            current = "⚠️ *Continuação...*\n" + ln
        else:
            current = (current + "\n" + ln) if current else ln
    if current:
        telegram.send_message(current, parse_mode="MarkdownV2")


def build_and_send_report(
    results: dict[str, Any],
    telegram: TelegramNotifier,
    target_owner: str,
    get_author_fn: Callable[[str, str], str],
) -> None:
    """Build and send a sanitised security report via Telegram.

    Each repository block is sent as its own message with an inline button
    that opens the repository on GitHub. Vulnerability links use the exact
    commit hash so they point to the precise file version where the secret
    was found — not necessarily the default branch.
    """
    esc = telegram.escape

    header = (
        "🔐 *Relatório do Security Scanner*\n\n"
        f"📊 *Repos escaneados:* {results['scanned']}/{results['total_repositories']}\n"
        f"❌ *Erros de scan:* {results['failed']}\n"
        f"⚠️ *Total de achados:* {results['total_findings']}\n"
        f"📦 *Repos com problemas:* {len(results['repositories_with_findings'])}\n"
        f"👤 Dono: `{esc(target_owner)}`"
    )
    _send_lines([header], telegram)

    repos_with_findings = sorted(
        results["repositories_with_findings"],
        key=lambda x: len(x["findings"]),
        reverse=True,
    )

    for repo_data in repos_with_findings:
        repo_name = repo_data["repository"]
        findings = repo_data["findings"]
        _send_repo_block(repo_name, findings, telegram, esc, get_author_fn)

    if results["scan_errors"]:
        error_lines = [f"❌ *Erros de Scan \\({len(results['scan_errors'])}\\):*"]
        for error in results["scan_errors"]:
            repo_short = error["repository"].split("/")[-1]
            error_msg = error["error"][:40]
            error_lines.append(f"  • {esc(repo_short)}: {esc(error_msg)}")
        _send_lines(error_lines, telegram)


def _send_repo_block(
    repo_name: str,
    findings: list[dict],
    telegram: TelegramNotifier,
    esc: Callable[[str | None], str],
    get_author_fn: Callable[[str, str], str],
) -> None:
    """Send a single repo's findings as one Telegram message with a button."""
    lines = [f"📦 *{esc(repo_name)}* \\({len(findings)} achados\\):"]

    max_displayed = 10
    for finding in findings[:max_displayed]:
        rule_id = esc(finding["rule_id"])
        file_path = finding["file"]
        line_no = finding["line"]
        full_commit = finding.get("full_commit") or finding.get("commit", "")

        author = get_author_fn(repo_name, full_commit)
        if author and author != "unknown":
            author_link = f"[{esc(author)}](https://github.com/{author})"
        else:
            author_link = "unknown"

        encoded_path = quote(file_path, safe="/")
        # Use the commit hash for a stable, branch-independent permalink
        ref = full_commit if full_commit else "HEAD"
        vuln_url = f"https://github.com/{repo_name}/blob/{ref}/{encoded_path}#L{line_no}"
        lines.append(f"  • [{rule_id}]({vuln_url}) — {author_link}")

    if len(findings) > max_displayed:
        lines.append(f"  \\+ {len(findings) - max_displayed} outros achados\\.\\.\\.")

    text = "\n".join(lines)
    if len(text) > _MAX_LEN:
        text = telegram._truncate(text)

    inline_keyboard = {
        "inline_keyboard": [[
            {"text": "🔍 Ver no GitHub", "url": f"https://github.com/{repo_name}"}
        ]]
    }
    telegram.send_message(text, parse_mode="MarkdownV2", reply_markup=inline_keyboard)


def send_error_notification(
    telegram: TelegramNotifier,
    target_owner: str,
    error_message: str,
) -> None:
    """Send a plain error notification via Telegram."""
    esc = telegram.escape
    text = (
        "🔐 *Security Scanner — Erro*\n\n"
        f"❌ {esc(error_message)}\n\n"
        f"👤 Owner: `{esc(target_owner)}`"
    )
    telegram.send_message(text, parse_mode="MarkdownV2")
