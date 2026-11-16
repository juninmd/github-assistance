/** Telegram summary builder for PR Assistant results. */
import { TelegramNotifier } from "../../notifications/telegram.ts";

type Item = Record<string, any>;
const esc = TelegramNotifier.escapeHtml;
function section(items: Item[], icon: string, title: string, max = 5, extra: string[] = []): string[] {
  if (!items.length) return [];
  const lines = [`\n${icon} <b>${title}</b> (<code>${items.length}</code>)`];
  for (const it of items.slice(0, max)) {
    const repo = it.repository ?? "", n = it.pr ?? "?";
    const parts = [`${esc(repo)}#${n}`];
    for (const f of extra) if (it[f]) parts.push(`<b>${esc(it[f])}</b>`);
    parts.push(`<i>${esc(it.title ?? "")}</i>`);
    lines.push(`  └ <a href="https://github.com/${repo}/pull/${n}">${parts.join(" — ")}</a>`);
  }
  if (items.length > max) lines.push(`  └ <i>+ ${items.length - max} outros...</i>`);
  return lines;
}
function skippedSection(skipped: Item[]): string[] {
  if (!skipped.length) return [];
  const lines = [`\n⏭️ <b>Pulos / Pendentes</b> (<code>${skipped.length}</code>)`];
  const byReason = new Map<string, Item[]>();
  for (const it of skipped) { const r = it.reason ?? "unknown"; byReason.set(r, [...(byReason.get(r) ?? []), it]); }
  for (const [reason, items] of byReason) {
    lines.push(`  🔹 <b>${esc(reason)}</b> (<code>${items.length}</code>):`);
    for (const it of items.slice(0, 3)) lines.push(`    └ <a href="https://github.com/${it.repository ?? ""}/pull/${it.pr ?? "?"}">${esc(it.repository ?? "")}#${it.pr ?? "?"}</a>`);
    if (items.length > 3) lines.push(`    └ <i>+ ${items.length - 3} outros...</i>`);
  }
  return lines;
}
export async function buildAndSendSummary(results: Record<string, Item[]>, tg: Pick<TelegramNotifier, "sendMessage">, owner: string): Promise<void> {
  const merged = results.merged ?? [], conflicts = results.conflicts_resolved ?? [], failures = results.pipeline_failures ?? [], skipped = results.skipped ?? [];
  const total = merged.length + conflicts.length + failures.length + skipped.length;
  if (!total) return;
  const lines = ["📦 <b>PR ASSISTANT SUMMARY</b>", `👤 <b>Owner:</b> <code>${esc(owner)}</code>`, "──────────────────────",
    ...section(merged, "✅", "Merged", 10), ...section(conflicts, "🔧", "Conflitos Resolvidos", 5), ...section(failures, "❌", "Falhas de Pipeline", 5, ["state"]),
    ...skippedSection(skipped), "\n──────────────────────", `📊 <b>Total Processado:</b> <code>${total}</code>`];
  await tg.sendMessage(lines.join("\n"), "HTML");
}
