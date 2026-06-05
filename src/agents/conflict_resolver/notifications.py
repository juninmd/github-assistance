"""Telegram notices for ConflictResolverAgent."""

from contextlib import suppress
from typing import Any


def send_resolution_notice(telegram: Any, pr: Any, msg: str) -> None:
    with suppress(Exception):
        telegram.send_message(
            f"<b>CONFLITO RESOLVIDO</b>\n"
            f"<b>Repo:</b> <code>{telegram.escape_html(pr.base.repo.full_name)}</code>\n"
            f'<b>PR:</b> <a href="{pr.html_url}">#{pr.number}</a> - '
            f"{telegram.escape_html(pr.title)}\n"
            f"{telegram.escape_html(msg)}",
            parse_mode="HTML",
        )


def send_manual_notice(telegram: Any, pr: Any, error: str) -> None:
    with suppress(Exception):
        telegram.send_message(
            f"<b>CONFLITO MANUAL NECESSARIO</b>\n"
            f"<b>Repo:</b> <code>{telegram.escape_html(pr.base.repo.full_name)}</code>\n"
            f'<b>PR:</b> <a href="{pr.html_url}">#{pr.number}</a> - '
            f"{telegram.escape_html(pr.title)}\n"
            f"<pre>{telegram.escape_html(error[:300])}</pre>",
            parse_mode="HTML",
        )


def send_pipeline_fix_notice(telegram: Any, pr: Any, msg: str) -> None:
    with suppress(Exception):
        telegram.send_message(
            f"<b>PIPELINE CORRIGIDO</b>\n"
            f"<b>Repo:</b> <code>{telegram.escape_html(pr.base.repo.full_name)}</code>\n"
            f'<b>PR:</b> <a href="{pr.html_url}">#{pr.number}</a> - '
            f"{telegram.escape_html(pr.title)}\n"
            f"{telegram.escape_html(msg)}",
            parse_mode="HTML",
        )


def send_pipeline_manual_notice(telegram: Any, pr: Any, error: str) -> None:
    with suppress(Exception):
        telegram.send_message(
            f"<b>PIPELINE MANUAL NECESSARIO</b>\n"
            f"<b>Repo:</b> <code>{telegram.escape_html(pr.base.repo.full_name)}</code>\n"
            f'<b>PR:</b> <a href="{pr.html_url}">#{pr.number}</a> - '
            f"{telegram.escape_html(pr.title)}\n"
            f"<pre>{telegram.escape_html(error[:300])}</pre>",
            parse_mode="HTML",
        )


def send_summary_notice(
    telegram: Any,
    resolved: list[dict],
    manual: list[dict],
    pipeline_fixed: list[dict] | None = None,
    pipeline_manual: list[dict] | None = None,
) -> None:
    esc = telegram.escape_html
    pipeline_fixed = pipeline_fixed or []
    pipeline_manual = pipeline_manual or []
    lines = [
        "<b>CONFLICT RESOLVER</b>",
        f"<b>Resolvidos:</b> <code>{len(resolved)}</code>",
        f"<b>Manuais:</b> <code>{len(manual)}</code>",
        f"<b>Pipelines corrigidos:</b> <code>{len(pipeline_fixed)}</code>",
        f"<b>Pipelines manuais:</b> <code>{len(pipeline_manual)}</code>",
    ]
    _add_items(lines, resolved, "msg", esc)
    _add_items(lines, manual, "error", esc)
    _add_items(lines, pipeline_fixed, "msg", esc)
    _add_items(lines, pipeline_manual, "error", esc)
    telegram.send_message("\n".join(lines), parse_mode="HTML")


def _add_items(lines: list[str], items: list[dict], field: str, esc: Any) -> None:
    for item in items[:5]:
        url = f"https://github.com/{item['repo']}/pull/{item['pr']}"
        lines.append(
            f'  <a href="{url}">{esc(item["repo"])} #{item["pr"]}</a> - '
            f'<i>{esc(item[field])}</i>'
        )
