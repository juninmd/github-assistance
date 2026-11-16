/** Execution reporting (Telegram) and results saving. */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { TelegramNotifier } from "../../notifications/telegram.ts";

export function saveResults(agentName: string, results: Record<string, any>, dir = join(process.cwd(), "results")): string {
  mkdirSync(dir, { recursive: true });
  const ts = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 15).replace(/^(\d{8})(\d{6}).*/, "$1_$2");
  const file = join(dir, `${agentName}_${ts}.json`);
  writeFileSync(file, JSON.stringify(results, null, 2));
  console.log(`Results saved to ${file}`);
  return file;
}

const SEP = "─".repeat(22);
export const formatDuration = (s: number) => (s < 60 ? `${s.toFixed(0)}s` : `${Math.floor(s / 60)}m${String(Math.floor(s % 60)).padStart(2, "0")}s`);
type Esc = (t?: string | null) => string;
const first = (v: unknown, n: number) => String(v).split("\n")[0].slice(0, n);

function header(agent: string, r: Record<string, any>, esc: Esc): string[] {
  const m = r._metrics ?? {};
  const lines = ["🤖 <b>GITHUB ASSISTANCE REPORT</b>", `📅 <code>${esc(new Date().toISOString().slice(0, 19).replace("T", " "))}</code>`,
    `👤 <b>Agente:</b> <code>${esc(agent.replace(/-/g, " ").toUpperCase())}</code>`,
    `⏱️ <b>Duração:</b> <code>${esc(m.duration_seconds != null ? formatDuration(m.duration_seconds) : "—")}</code>`, SEP];
  if (m.success_rate != null) lines.push(`📊 <b>Taxa de sucesso:</b> <code>${Number(m.success_rate).toFixed(0)}%</code>`);
  return lines;
}
function allAgents(r: Record<string, any>, esc: Esc): string[] {
  const lines: string[] = []; let ok = 0, bad = 0;
  for (const [name, res] of Object.entries<any>(r)) {
    if (name.startsWith("_")) continue;
    if (res && "error" in res) { bad++; lines.push(`❌ *${esc(name)}*`, `  └ ⚠️ \`${esc(first(res.error, 100))}\``); } else { ok++; lines.push(`✅ *${esc(name)}*`); }
  }
  lines.push(SEP, `📊 <b>Resumo:</b> ✅ <code>${ok}</code> | ❌ <code>${bad}</code>`);
  return lines;
}
function seniorDev(r: Record<string, any>): string[] {
  const n = (k: string) => (r[k] ?? []).length, sec = n("security_tasks"), cicd = n("cicd_tasks"), feat = n("feature_tasks"), debt = n("tech_debt_tasks");
  if (!(sec || cicd || feat || debt)) return [];
  const l = ["\n🛠️ <b>Tarefas Criadas:</b>"];
  if (sec) l.push(`  🛡️ Segurança: <b>${sec}</b>`); if (cicd) l.push(`  ⚙️ CI/CD: <b>${cicd}</b>`);
  if (feat) l.push(`  ✨ Features: <b>${feat}</b>`); if (debt) l.push(`  🧹 Débito Técnico: <b>${debt}</b>`);
  return l;
}
function processedFailed(r: Record<string, any>, esc: Esc): string[] {
  const lines: string[] = [], p = r.processed ?? r.merged ?? r.resolved ?? [], f = r.failed ?? [];
  const size = (v: any) => (Array.isArray(v) ? v.length : v && typeof v === "object" ? Object.keys(v).length : 0);
  if (size(p) > 0) lines.push(`\n📈 <b>Itens Processados:</b> <code>${size(p)}</code>`);
  else if (typeof p === "number" && p > 0) lines.push(`\n📈 <b>Itens Processados:</b> <code>${p}</code>`);
  if (size(f) > 0) {
    lines.push(`❌ <b>Falhas:</b> <code>${size(f)}</code>`);
    for (const x of (Array.isArray(f) ? f : Object.values(f)).slice(0, 3)) lines.push(`  └ <code>${esc((x as any).repository ?? "unknown")}</code>: <i>${esc(first((x as any).error ?? "unknown", 50))}</i>`);
  }
  return lines;
}
function single(agent: string, r: Record<string, any>, esc: Esc): string[] {
  if ("error" in r) return ["💥 <b>STATUS: FALHA CRÍTICA</b>", `⚠️ <b>Erro:</b> <code>${esc(first(r.error, 250))}</code>`];
  return ["🚀 <b>STATUS: OPERAÇÃO CONCLUÍDA</b>", ...(agent === "senior-developer" ? seniorDev(r) : []), ...processedFailed(r, esc)];
}

export async function sendExecutionReport(tg: TelegramNotifier, agent: string, results: Record<string, any>): Promise<void> {
  if (agent === "pr-assistant") return;
  const esc = TelegramNotifier.escapeHtml;
  const lines = [...header(agent, results, esc), ...(agent === "all" ? allAgents(results, esc) : single(agent, results, esc))];
  await tg.sendMessage(lines.join("\n"), "HTML");
}
