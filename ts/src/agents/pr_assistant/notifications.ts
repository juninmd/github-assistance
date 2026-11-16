/** Comment/Telegram notification helpers for the PR Assistant (best-effort: never break the merge workflow). */
import type { GithubClient, PR } from "../../github/client.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";
import { buildOriginMetadata } from "../core/utils.ts";

const ORIGIN = buildOriginMetadata("pr_assistant");
const esc = TelegramNotifier.escapeHtml;
type Tg = Pick<TelegramNotifier, "sendMessage">;
const appendOrigin = (body: string) => `${body}\n\n${ORIGIN}`;
const SEP = "──────────────────────────────";

/** [summary, files, model] from a conflict resolver message. */
export function parseResolutionMsg(msg: string): [string, string, string] {
  const lines = msg.split(/\r?\n/);
  let files = "", model = "";
  for (const l of lines.slice(1)) {
    if (l.startsWith("**Files:**")) files = l.replace("**Files:**", "").trim();
    else if (l.startsWith("**Model/Provider:**")) model = l.replace("**Model/Provider:**", "").trim();
  }
  return [lines[0] ?? msg, files, model];
}
async function toGithub(gh: GithubClient, pr: PR, body: string) { try { await gh.commentOnPr(pr, body); } catch { /* logged upstream */ } }
async function toTelegram(tg: Tg, text: string) { try { await tg.sendMessage(text, "HTML"); } catch { /* best-effort */ } }
async function hasMarker(gh: GithubClient, pr: PR, marker: string, comments?: any[] | null): Promise<boolean | null> {
  try { return (comments ?? (await gh.getIssueComments(pr.base.repo.full_name, pr.number))).some((c) => (c.body ?? "").includes(marker)); }
  catch { return null; }
}
const prLine = (pr: PR) => `🔀 <b>PR:</b> <a href="${pr.html_url}">#${pr.number}</a> — <b>${esc(pr.title)}</b>`;
const branches = (pr: PR) => `🌿 <b>Branch:</b> <code>${esc(pr.head?.ref ?? "unknown")}</code> ➔ <code>${esc(pr.base?.ref ?? "unknown")}</code>`;

export async function notifyConflictResolved(gh: GithubClient, tg: Tg, pr: PR, msg: string) {
  const author = pr.user ? `@${pr.user.login}` : "@contributor";
  const [summary, files, model] = parseResolutionMsg(msg);
  const c = ["✅ **Conflitos de Merge Resolvidos**\n", `Oi ${author}! Os conflitos de merge do PR **#${pr.number}** foram resolvidos automaticamente.\n`, `**Resumo:** ${summary}`];
  if (files) c.push(`**Arquivos alterados:** ${files}`);
  if (model) c.push(`**Modelo utilizado:** \`${model}\``);
  c.push(`\n${ORIGIN}`);
  await toGithub(gh, pr, c.join("\n"));
  const t = ["✅ <b>CONFLITO RESOLVIDO</b>", "──────────────────────", `📦 <b>Repo:</b> <code>${esc(pr.base.repo.full_name)}</code>`,
    `🔀 <b>PR:</b> <a href="${pr.html_url}">#${pr.number}</a> — ${esc(pr.title)}`, `ℹ️ ${esc(summary)}`];
  if (files) t.push(`📝 <b>Arquivos:</b> <code>${esc(files)}</code>`);
  if (model) t.push(`🤖 <b>Modelo:</b> <code>${esc(model)}</code>`);
  await toTelegram(tg, t.join("\n"));
}
export async function notifyConflicts(gh: GithubClient, tg: Tg, pr: PR, comments?: any[] | null) {
  if ((await hasMarker(gh, pr, "⚠️ **Conflitos de Merge Detectados**", comments)) !== false) return;
  await toGithub(gh, pr, appendOrigin("⚠️ **Conflitos de Merge Detectados**\n\nEste PR tem conflitos de merge que não puderam ser resolvidos automaticamente. Por favor, resolva manualmente."));
  await toTelegram(tg, `🚨 <b>CONFLITO DE MERGE DETECTADO</b> 🚨\n⚠️ <i>Atenção necessária</i>\n${SEP}\n📁 <b>Repositório:</b> <code>${esc(pr.base.repo.full_name)}</code>\n${branches(pr)}\n${prLine(pr)}\n` +
    `👤 <b>Autor:</b> <code>${esc(pr.user?.login ?? "unknown")}</code>\n${SEP}\n❌ Os conflitos não puderam ser resolvidos de forma automatizada. Resolução manual necessária.`);
}
export async function notifyMergeFailed(gh: GithubClient, tg: Tg, pr: PR, error: string, comments?: any[] | null) {
  if ((await hasMarker(gh, pr, "<!-- merge-failed -->", comments)) !== false) return;
  await toGithub(gh, pr, appendOrigin("<!-- merge-failed -->\n❌ **Merge falhou**\n\nTentei realizar o merge deste PR mas ocorreu um erro:\n\n```\n" + error +
    "\n```\n\nPor favor, verifique as permissões do repositório ou se há proteções de branch que impedem o merge automático."));
  await toTelegram(tg, `💥 <b>FALHA AO REALIZAR MERGE</b> 💥\n${SEP}\n📁 <b>Repositório:</b> <code>${esc(pr.base.repo.full_name)}</code>\n${branches(pr)}\n${prLine(pr)}\n${SEP}\n🛑 <b>Erro reportado:</b>\n<pre>${esc(error.slice(0, 400))}</pre>`);
}
export async function notifyPipelinePending(gh: GithubClient, tg: Tg, pr: PR, state: string, comments?: any[] | null) {
  if ((await hasMarker(gh, pr, "<!-- pipeline-pending -->", comments)) !== false) return;
  await toGithub(gh, pr, appendOrigin(`<!-- pipeline-pending -->\n⏳ **Aguardando pipeline**\n\nO pipeline de CI/CD está com estado \`${state}\`. O merge será realizado automaticamente assim que todas as verificações passarem.`));
  await toTelegram(tg, `⏳ <b>AGUARDANDO PIPELINE</b> ⏳\n${SEP}\n📁 <b>Repositório:</b> <code>${esc(pr.base.repo.full_name)}</code>\n${branches(pr)}\n${prLine(pr)}\n${SEP}\n⚙️ <b>Status da CI:</b> <code>${esc(state)}</code>\nO merge ocorrerá automaticamente após a conclusão com sucesso do workflow.`);
}
export async function notifyMerged(gh: GithubClient, pr: PR, comments?: any[] | null) {
  if ((await hasMarker(gh, pr, "<!-- pr-merged -->", comments)) === true) return; // Python: a read failure still posts
  await toGithub(gh, pr, appendOrigin("<!-- pr-merged -->\n🎉 **Pull Request mesclado com sucesso!**\n\nO merge deste PR foi realizado automaticamente após a validação de todas as políticas e checks de CI/CD."));
}
