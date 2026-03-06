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
            repo = esc(item.get("repository", ""))
            pr_num = item.get("pr", "?")
            title = esc(item.get("title", ""))
            lines.append(f"  • `{repo}`\\#{pr_num} — {title}")
        if len(merged) > 10:
            lines.append(f"  \\+ {len(merged) - 10} outros\\.\\.\\.")

    if conflicts:
        lines.append(f"\n🔧 *Conflitos resolvidos \\({len(conflicts)}\\):*")
        for item in conflicts[:5]:
            repo = esc(item.get("repository", ""))
            pr_num = item.get("pr", "?")
            lines.append(f"  • `{repo}`\\#{pr_num}")

    if pipeline_failures:
        lines.append(f"\n❌ *Pipeline failures \\({len(pipeline_failures)}\\):*")
        for item in pipeline_failures[:5]:
            repo = esc(item.get("repository", ""))
            pr_num = item.get("pr", "?")
            state = esc(item.get("state", ""))
            lines.append(f"  • `{repo}`\\#{pr_num} — {state}")

    if skipped:
        lines.append(f"\n⏭️ *Skipped \\({len(skipped)}\\):*")
        reasons: dict[str, int] = {}
        for item in skipped:
            reason = item.get("reason", "unknown")
            reasons[reason] = reasons.get(reason, 0) + 1
        for reason, count in reasons.items():
            lines.append(f"  • {esc(reason)}: *{count}*")

    telegram.send_message("\n".join(lines), parse_mode="MarkdownV2")
