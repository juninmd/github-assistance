import { TelegramNotifier } from "../../notifications/telegram.ts";
const esc = TelegramNotifier.escapeHtml, MAX_LEN = 3800;
const trunc = (t: string) => (t.length > TelegramNotifier.MAX_LENGTH ? t.slice(0, TelegramNotifier.MAX_LENGTH) : t);
const encPath = (p: string) => p.split("/").map(encodeURIComponent).join("/");

async function sendLines(lines: string[], t: TelegramNotifier) {
  let cur = "";
  for (let ln of lines) {
    if (ln.length > MAX_LEN) ln = trunc(ln);
    if (cur && cur.length + ln.length + 1 > MAX_LEN) { await t.sendMessage(cur, "HTML"); cur = "⚠️ <b>Continuação...</b>\n" + ln; }
    else cur = cur ? cur + "\n" + ln : ln;
  }
  if (cur) await t.sendMessage(cur, "HTML");
}

export async function buildAndSendReport(r: Record<string, any>, t: TelegramNotifier, owner: string, getAuthor: (repo: string, sha: string) => Promise<string>) {
  await sendLines([`🔐 <b>Relatório do Security Scanner</b>\n\n📊 <b>Repos escaneados:</b> ${r.scanned}/${r.total_repositories}\n❌ <b>Erros de scan:</b> ${r.failed}\n⚠️ <b>Total de achados:</b> ${r.total_findings}\n📦 <b>Repos com problemas:</b> ${r.repositories_with_findings.length}\n⏰ <b>Workflows cron proibidos:</b> ${r.total_cron_workflows ?? 0}\n👤 Dono: <code>${esc(owner)}</code>`], t);
  for (const rd of [...r.repositories_with_findings].sort((a: any, b: any) => b.findings.length - a.findings.length)) await sendRepoBlock(rd.repository, rd.findings, t, getAuthor);
  if (r.repositories_with_cron?.length) await sendCronPolicyBlock(r.repositories_with_cron, t);
  if (r.scan_errors.length) await sendLines([`❌ <b>Erros de Scan (${r.scan_errors.length}):</b>`, ...r.scan_errors.map((e: any) => `  • ${esc(e.repository.split("/").pop())}: ${esc(String(e.error).slice(0, 40))}`)], t);
}

async function sendRepoBlock(repo: string, findings: any[], t: TelegramNotifier, getAuthor: (repo: string, sha: string) => Promise<string>) {
  const lines = [`📦 <b>${esc(repo)}</b> (${findings.length} achados):`], max = 10;
  for (const f of findings.slice(0, max)) {
    const sha = f.full_commit || f.commit || "", author = await getAuthor(repo, sha);
    const link = author && author !== "unknown" ? `<a href="https://github.com/${author}">${esc(author)}</a>` : "unknown";
    lines.push(`  • <a href="https://github.com/${repo}/blob/${sha || "HEAD"}/${encPath(f.file)}#L${f.line}">${esc(f.rule_id)}</a> — ${link}`);
  }
  if (findings.length > max) lines.push(`  + ${findings.length - max} outros achados...`);
  await t.sendMessage(trunc(lines.join("\n")), "HTML", { inline_keyboard: [[{ text: "🔍 Ver no GitHub", url: `https://github.com/${repo}` }]] });
}

async function sendCronPolicyBlock(repos: any[], t: TelegramNotifier) {
  const total = repos.reduce((n, r) => n + r.cron_workflows.length, 0);
  const lines = [`⏰ <b>Política: workflows cron proibidos (${total})</b>`, "GitHub Actions agendadas por cron consomem minutos de runner continuamente. Troque por <code>workflow_dispatch</code> ou gatilhos por evento."];
  for (const rd of [...repos].sort((a, b) => b.cron_workflows.length - a.cron_workflows.length)) {
    lines.push(`\n📦 <b>${esc(rd.repository)}</b>`);
    for (const wf of rd.cron_workflows.slice(0, 10)) lines.push(`  • <a href="https://github.com/${rd.repository}/blob/HEAD/${encPath(wf.file)}#L${wf.line}">${esc(wf.file)}</a> — <code>${esc(wf.cron ?? "")}</code>`);
    const extra = rd.cron_workflows.length - 10; if (extra > 0) lines.push(`  + ${extra} outro(s)...`);
  }
  await sendLines(lines, t);
}

export const sendErrorNotification = (t: TelegramNotifier, owner: string, msg: string) =>
  t.sendMessage(`🔐 <b>Security Scanner — Erro</b>\n\n❌ ${esc(msg)}\n\n👤 Owner: <code>${esc(owner)}</code>`, "HTML");
