"""Telegram summary builder for PR Assistant results."""

from src.notifications.telegram import TelegramNotifier


def _build_section(
    items: list[dict],
    icon: str,
    title: str,
    esc,
    max_items: int = 5,
    extra_fields: list[str] | None = None,
) -> list[str]:
    if not items:
        return []
    lines = [f"\n{icon} <b>{title}</b> (<code>{len(items)}</code>)"]
    for item in items[:max_items]:
        repo = item.get("repository", "")
        pr_num = item.get("pr", "?")
        url = f"https://github.com/{repo}/pull/{pr_num}"
        parts = [f"{esc(repo)}#{pr_num}"]
        if extra_fields:
            for field in extra_fields:
                val = item.get(field, "")
                if val:
                    parts.append(f"<b>{esc(val)}</b>")
        title_val = esc(item.get("title", ""))
        parts.append(f"<i>{title_val}</i>")
        lines.append(f'  └ <a href="{url}">{" — ".join(parts)}</a>')
    if len(items) > max_items:
        lines.append(f"  └ <i>+ {len(items) - max_items} outros...</i>")
    return lines


def _build_skipped_section(skipped: list[dict], esc) -> list[str]:
    if not skipped:
        return []
    lines = [f"\n⏭️ <b>Pulos / Pendentes</b> (<code>{len(skipped)}</code>)"]
    reasons_map: dict[str, list] = {}
    for item in skipped:
        reason = item.get("reason", "unknown")
        reasons_map.setdefault(reason, []).append(item)
    for reason, items in reasons_map.items():
        lines.append(f"  🔹 <b>{esc(reason)}</b> (<code>{len(items)}</code>):")
        for item in items[:3]:
            repo = item.get("repository", "")
            pr_num = item.get("pr", "?")
            url = f"https://github.com/{repo}/pull/{pr_num}"
            lines.append(f'    └ <a href="{url}">{esc(repo)}#{pr_num}</a>')
        if len(items) > 3:
            lines.append(f"    └ <i>+ {len(items) - 3} outros...</i>")
    return lines


def build_and_send_summary(
    results: dict,
    telegram: TelegramNotifier,
    target_owner: str,
) -> None:
    esc = telegram.escape_html
    merged = results.get("merged", [])
    conflicts = results.get("conflicts_resolved", [])
    pipeline_failures = results.get("pipeline_failures", [])
    skipped = results.get("skipped", [])

    total = len(merged) + len(conflicts) + len(pipeline_failures) + len(skipped)
    if total == 0:
        return

    lines = [
        "📦 <b>PR ASSISTANT SUMMARY</b>",
        f"👤 <b>Owner:</b> <code>{esc(target_owner)}</code>",
        "──────────────────────",
    ]
    lines.extend(_build_section(merged, "✅", "Merged", esc, max_items=10))
    lines.extend(_build_section(conflicts, "🔧", "Conflitos Resolvidos", esc, max_items=5))
    lines.extend(
        _build_section(
            pipeline_failures, "❌", "Falhas de Pipeline", esc, max_items=5, extra_fields=["state"]
        )
    )
    lines.extend(_build_skipped_section(skipped, esc))

    lines.append("\n──────────────────────")
    lines.append(f"📊 <b>Total Processado:</b> <code>{total}</code>")

    telegram.send_message("\n".join(lines), parse_mode="HTML")
