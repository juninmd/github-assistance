/** Telegram notices for ConflictResolverAgent (best-effort). */
import type { TelegramNotifier } from "../../notifications/telegram.ts";
import { card, esc, prButton, reasonLabel } from "../../notifications/telegram-format.ts";

type Tg = Pick<TelegramNotifier, "sendMessage">;
const send = async (tg: Tg, pr: any, text: string) => { try { await tg.sendMessage(text, "HTML", prButton(pr)); } catch { /* best-effort */ } };
export const sendResolutionNotice = (tg: Tg, pr: any, msg: string) => send(tg, pr, card("✅", "CONFLITO RESOLVIDO", pr, [`ℹ️ ${esc(msg.split("\n")[0] ?? msg)}`]));
export const sendManualNotice = (tg: Tg, pr: any, error: string) =>
  send(tg, pr, card("🚫", "CONFLITO: RESOLUÇÃO MANUAL NECESSÁRIA", pr, ["ℹ️ O PR continua aberto e foi marcado com <code>needs-manual-conflict-resolution</code>.", `<pre>${esc(error.slice(0, 300))}</pre>`]));
export const sendPipelineFixNotice = (tg: Tg, pr: any, msg: string) => send(tg, pr, card("🛠️", "PIPELINE CORRIGIDO", pr, [`ℹ️ ${esc(msg.split("\n")[0] ?? msg)}`]));
export const sendPipelineManualNotice = (tg: Tg, pr: any, error: string) =>
  send(tg, pr, card("🚫", "PIPELINE: CORREÇÃO MANUAL NECESSÁRIA", pr, [`<pre>${esc(error.slice(0, 300))}</pre>`]));
type Item = Record<string, any>;
function addItems(lines: string[], items: Item[], field: string) {
  for (const it of items.slice(0, 5)) lines.push(`  └ <a href="https://github.com/${it.repo}/pull/${it.pr}">${esc(it.repo)}#${it.pr}</a> — <i>${esc(reasonLabel(String(it[field] ?? "")).slice(0, 120))}</i>`);
}
export async function sendSummaryNotice(tg: Tg, resolved: Item[], manual: Item[], pipelineFixed: Item[] = [], pipelineManual: Item[] = []) {
  const lines = ["🛠️ <b>CONFLICT RESOLVER</b>", "──────────────────────", `✅ <b>Conflitos resolvidos:</b> <code>${resolved.length}</code>`, `🚫 <b>Conflitos manuais:</b> <code>${manual.length}</code>`,
    `🔧 <b>Pipelines corrigidos:</b> <code>${pipelineFixed.length}</code>`, `🚫 <b>Pipelines manuais:</b> <code>${pipelineManual.length}</code>`];
  addItems(lines, resolved, "msg"); addItems(lines, manual, "error"); addItems(lines, pipelineFixed, "msg"); addItems(lines, pipelineManual, "error");
  await tg.sendMessage(lines.join("\n"), "HTML");
}
