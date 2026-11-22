import { TelegramNotifier } from "../../notifications/telegram.ts";
const esc = TelegramNotifier.escapeHtml;

const HEADLINE: Record<string, string> = {
  REMOVE_FROM_HISTORY: "🔥 <b>Secret Removida do Histórico</b>",
  AWAITING_APPROVAL: "⏳ <b>Secret real — aguardando sua aprovação para reescrever o histórico</b>",
  REMOVE_FAILED: "❌ <b>Falha ao remover a secret do histórico</b>",
};
export function buildFindingMessage(repo: string, finding: Record<string, any>, originalLine: string, action: string): string {
  const preview = originalLine ? esc(originalLine.slice(0, 200)) : "<i>não disponível</i>";
  return `${HEADLINE[action] ?? "✅ <b>Secret Falso Positivo (Ignorado)</b>"}\n\n` +
    `📦 Repositório: <code>${esc(repo)}</code>\n📄 Arquivo: <code>${esc(finding.file ?? "unknown")}</code> (Linha ${finding.line ?? 0})\n` +
    `🤖 Motivo: <i>${esc(finding._reason ?? "No reason provided")}</i>\n\n📝 <b>Conteúdo original (redactado):</b>\n<code>${preview}</code>`;
}
export const getFindingButtons = (repoUrl: string, commitUrl: string, fileLineUrl: string) =>
  [[{ text: "🔗 Repositório", url: repoUrl }, { text: "📌 Commit", url: commitUrl }], [{ text: "📄 Arquivo+Linha", url: fileLineUrl }]];

export const sendFindingNotification = (t: TelegramNotifier, o: { repo: string; finding: Record<string, any>; action: string; originalLine: string; commitUrl: string; fileLineUrl: string; repoUrl: string }) =>
  t.sendMessage(buildFindingMessage(o.repo, o.finding, o.originalLine, o.action), "HTML", { inline_keyboard: getFindingButtons(o.repoUrl, o.commitUrl, o.fileLineUrl) });
export const sendErrorNotification = (t: TelegramNotifier, owner: string, msg: string) =>
  t.sendMessage(`🔐 <b>Secret Remover — Erro</b>\n\n❌ ${esc(msg)}\n\n👤 Owner: <code>${esc(owner)}</code>`, "HTML");
