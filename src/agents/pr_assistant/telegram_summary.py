"""Telegram summary builder for PR Assistant results."""
from src.notifications.telegram import TelegramNotifier


def build_and_send_summary(
    results: dict,
    telegram: TelegramNotifier,
    target_owner: str,
) -> None:
    """Build and send a Telegram summary of PR processing results."""
    esc = telegram.escape
    merged = results.get("merged", [])
    conflicts = results.get("conflicts_resolved", [])
    pipeline_failures = results.get("pipeline_failures", [])
    skipped = results.get("skipped", [])

    total = len(merged) + len(conflicts) + len(pipeline_failures) + len(skipped)
    if total == 0:
        return

    lines = [
        "🤖 *PR Assistant — Resumo*",
        f"👤 Owner: `{esc(target_owner)}`",
        "",
    ]

    if merged:
        lines.append(f"✅ *Merged \\({len(merged)}\\):*")
        for item in merged[:10]:
            repo = item.get("repository", "")
            pr_num = item.get("pr", "?")
            title = esc(item.get("title", ""))
            url = f"https://github.com/{repo}/pull/{pr_num}"
            lines.append(f"  • [{esc(repo)}\\#{pr_num}]({url}) — {title}")
        if len(merged) > 10:
            lines.append(f"  \\+ {len(merged) - 10} outros\\.\\.\\.")

    if conflicts:
        lines.append(f"\n🔧 *Conflitos resolvidos \\({len(conflicts)}\\):*")
        for item in conflicts[:5]:
            repo = item.get("repository", "")
            pr_num = item.get("pr", "?")
            title = esc(item.get("title", ""))
            url = f"https://github.com/{repo}/pull/{pr_num}"
            lines.append(f"  • [{esc(repo)}\\#{pr_num}]({url}) — {title}")

    if pipeline_failures:
        lines.append(f"\n❌ *Pipeline failures \\({len(pipeline_failures)}\\):*")
        for item in pipeline_failures[:5]:
            repo = item.get("repository", "")
            pr_num = item.get("pr", "?")
            title = esc(item.get("title", ""))
            state = esc(item.get("state", ""))
            url = f"https://github.com/{repo}/pull/{pr_num}"
            lines.append(f"  • [{esc(repo)}\\#{pr_num}]({url}) — {state}: {title}")

    if skipped:
        lines.append(f"\n⏭️ *Skipped \\({len(skipped)}\\):*")
        reasons_map: dict[str, list] = {}
        for item in skipped:
            reason = item.get("reason", "unknown")
            reasons_map.setdefault(reason, []).append(item)

        for reason, items in reasons_map.items():
            lines.append(f"  • *{esc(reason)}* \\({len(items)}\\):")
            for item in items[:5]:
                repo = item.get("repository", "")
                pr_num = item.get("pr", "?")
                title = esc(item.get("title", ""))
                url = f"https://github.com/{repo}/pull/{pr_num}"
                lines.append(f"    ⁃ [{esc(repo)}\\#{pr_num}]({url}) — {title}")
            if len(items) > 5:
                lines.append(f"    ⁃ \\+ {len(items) - 5} outros\\.\\.\\.")

    telegram.send_message("\n".join(lines), parse_mode="MarkdownV2")
