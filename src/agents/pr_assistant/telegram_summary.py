"""Telegram summary builder for PR Assistant results."""
from collections import defaultdict

from src.notifications.telegram import TelegramNotifier


def build_and_send_summary(
    results: dict,
    telegram: TelegramNotifier,
    target_owner: str,
) -> None:
    """Build and send a Telegram summary of PR processing results."""
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

    if merged:
        lines.append(f"✅ <b>Merged</b> (<code>{len(merged)}</code>)")
        for item in merged[:10]:
            repo = item.get("repository", "")
            pr_num = item.get("pr", "?")
            title = esc(item.get("title", ""))
            url = f"https://github.com/{repo}/pull/{pr_num}"
            lines.append(f"  └ <a href=\"{url}\">{esc(repo)}#{pr_num}</a> — <i>{title}</i>")
        if len(merged) > 10:
            lines.append(f"  └ <i>+ {len(merged) - 10} outros...</i>")

    if conflicts:
        lines.append(f"\n🔧 <b>Conflitos Resolvidos</b> (<code>{len(conflicts)}</code>)")
        for item in conflicts[:5]:
            repo = item.get("repository", "")
            pr_num = item.get("pr", "?")
            title = esc(item.get("title", ""))
            url = f"https://github.com/{repo}/pull/{pr_num}"
            lines.append(f"  └ <a href=\"{url}\">{esc(repo)}#{pr_num}</a> — <i>{title}</i>")
        if len(conflicts) > 5:
            lines.append(f"  └ <i>+ {len(conflicts) - 5} outros...</i>")

    if pipeline_failures:
        lines.append(f"\n❌ <b>Falhas de Pipeline</b> (<code>{len(pipeline_failures)}</code>)")
        for item in pipeline_failures[:5]:
            repo = item.get("repository", "")
            pr_num = item.get("pr", "?")
            title = esc(item.get("title", ""))
            state = esc(item.get("state", ""))
            url = f"https://github.com/{repo}/pull/{pr_num}"
            lines.append(f"  └ <a href=\"{url}\">{esc(repo)}#{pr_num}</a> — <b>{state}</b>: <i>{title}</i>")
        if len(pipeline_failures) > 5:
            lines.append(f"  └ <i>+ {len(pipeline_failures) - 5} outros...</i>")

    if skipped:
        lines.append(f"\n⏭️ <b>Pulos / Pendentes</b> (<code>{len(skipped)}</code>)")
        reasons_map: dict[str, list] = defaultdict(list)
        for item in skipped:
            reason = item.get("reason", "unknown")
            reasons_map[reason].append(item)

        for reason, items in reasons_map.items():
            lines.append(f"  🔹 <b>{esc(reason)}</b> (<code>{len(items)}</code>):")
            for item in items[:3]:
                repo = item.get("repository", "")
                pr_num = item.get("pr", "?")
                url = f"https://github.com/{repo}/pull/{pr_num}"
                lines.append(f"    └ <a href=\"{url}\">{esc(repo)}#{pr_num}</a>")
            if len(items) > 3:
                lines.append(f"    └ <i>+ {len(items) - 3} outros...</i>")

    lines.append("\n──────────────────────")
    lines.append(f"📊 <b>Total Processado:</b> <code>{total}</code>")

    telegram.send_message("\n".join(lines), parse_mode="HTML")
