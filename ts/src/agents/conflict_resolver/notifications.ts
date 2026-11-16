/** Telegram notices for ConflictResolverAgent (best-effort). */
import { TelegramNotifier } from "../../notifications/telegram.ts";

const esc = TelegramNotifier.escapeHtml;
type Tg = Pick<TelegramNotifier, "sendMessage">;
const head = (title: string, pr: any) => `<b>${title}</b>\n<b>Repo:</b> <code>${esc(pr.base.repo.full_name)}</code>\n<b>PR:</b> <a href="${pr.html_url}">#${pr.number}</a> - ${esc(pr.title)}\n`;
const send = async (tg: Tg, text: string) => { try { await tg.sendMessage(text, "HTML"); } catch { /* best-effort */ } };
export const sendResolutionNotice = (tg: Tg, pr: any, msg: string) => send(tg, head("CONFLITO RESOLVIDO", pr) + esc(msg));
export const sendManualNotice = (tg: Tg, pr: any, error: string) => send(tg, head("CONFLITO MANUAL NECESSARIO", pr) + `<pre>${esc(error.slice(0, 300))}</pre>`);
export const sendPipelineFixNotice = (tg: Tg, pr: any, msg: string) => send(tg, head("PIPELINE CORRIGIDO", pr) + esc(msg));
export const sendPipelineManualNotice = (tg: Tg, pr: any, error: string) => send(tg, head("PIPELINE MANUAL NECESSARIO", pr) + `<pre>${esc(error.slice(0, 300))}</pre>`);
type Item = Record<string, any>;
function addItems(lines: string[], items: Item[], field: string) {
  for (const it of items.slice(0, 5)) lines.push(`  <a href="https://github.com/${it.repo}/pull/${it.pr}">${esc(it.repo)} #${it.pr}</a> - <i>${esc(it[field])}</i>`);
}
export async function sendSummaryNotice(tg: Tg, resolved: Item[], manual: Item[], pipelineFixed: Item[] = [], pipelineManual: Item[] = []) {
  const lines = ["<b>CONFLICT RESOLVER</b>", `<b>Resolvidos:</b> <code>${resolved.length}</code>`, `<b>Manuais:</b> <code>${manual.length}</code>`,
    `<b>Pipelines corrigidos:</b> <code>${pipelineFixed.length}</code>`, `<b>Pipelines manuais:</b> <code>${pipelineManual.length}</code>`];
  addItems(lines, resolved, "msg"); addItems(lines, manual, "error"); addItems(lines, pipelineFixed, "msg"); addItems(lines, pipelineManual, "error");
  await tg.sendMessage(lines.join("\n"), "HTML");
}
