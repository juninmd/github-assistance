/** Pure helpers for the Jules Tracker (activities parsing, reply shaping, Telegram updates). */
import { TelegramNotifier } from "../../notifications/telegram.ts";

type R = Record<string, any>;
const esc = TelegramNotifier.escapeHtml;
export const OPEN_PR_INSTRUCTION = "Ao finalizar, abra o pull request.";
export const DEFAULT_UNBLOCKING_ANSWER = "Pode prosseguir com seu melhor julgamento técnico. Use defaults seguros, mantenha o escopo pequeno, rode as validações aplicáveis e documente qualquer limitação.";
const key = (a: R): string => a.createTime || a.updateTime || "";
const byTime = (xs: R[]) => [...xs].sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0));
const stateOf = (s: R) => s.state ?? s.status;

export function extractRepositoryName(session: R): string {
  const source: string = session.sourceContext?.source ?? "", prefix = "sources/github/";
  return source.startsWith(prefix) ? source.slice(prefix.length) : source;
}

/** Latest Jules message not yet answered by the user (falls back to statusMessage when awaiting feedback). */
export function getPendingQuestion(session: R, activities: R[]): string | null {
  let lastUser = -1, pending: string | null = null;
  byTime(activities).forEach((a, i) => {
    if ("userMessaged" in a) { lastUser = i; pending = null; return; }
    const m = String(a.agentMessaged?.agentMessage ?? "").trim();
    if (m && i > lastUser) pending = m;
  });
  if (pending) return pending;
  const status = String(session.statusMessage ?? "").trim();
  return stateOf(session) === "AWAITING_USER_FEEDBACK" && status ? status : null;
}

export function latestActivityIsUserReply(activities: R[]): boolean {
  if (!activities.length) return false;
  const sorted = byTime(activities); // stable: the last of equal keys wins like Python max()
  return "userMessaged" in sorted[sorted.length - 1];
}

/** Guarantee every AI-authored Jules reply asks for a pull request. */
export function ensureOpenPrRequest(message: unknown): string {
  const n = String(message ?? "").trim();
  if (n.toLowerCase().includes("pull request") || /\bpr\b/i.test(n)) return n;
  return n ? `${n}\n\n${OPEN_PR_INSTRUCTION}` : OPEN_PR_INSTRUCTION;
}

/** A plan was generated but not yet approved (rare: plans are normally auto-approved within seconds). */
export function isPlanPending(activities: R[]): boolean {
  let has = false;
  for (const a of activities) { if ("planGenerated" in a) has = true; else if ("planApproved" in a) has = false; }
  return has;
}

export function getPendingPlan(activities: R[]): string | null {
  let plan: string | null = null;
  for (const a of byTime(activities)) {
    if (a.planGenerated) {
      const steps = a.planGenerated.planDescription || a.planGenerated.steps;
      plan = typeof steps === "string" ? steps : steps ? String(steps) : plan;
    } else if ("planApproved" in a) plan = null;
  }
  return plan;
}

export const formatQuestionDescription = (repo: string, id: string, q: string) => `[${repo}] session ${id}: ${q}`;
export const colorize = (text: string, color: string, reset = "\x1b[0m") => (process.env.NO_COLOR ? text : `${color}${text}${reset}`);
export const formatQuestionLog = (repo: string, id: string, url: string, q: string, color: string, reset = "\x1b[0m") =>
  `Found pending question\n  Repository: ${repo}\n  Session: ${id}\n  URL: ${url}\n  Question: ${colorize(q, color, reset)}`;
export const formatAnswerLog = (a: string, color: string, reset = "\x1b[0m") => `Generated answer\n  LLM: ${colorize(a, color, reset)}`;

const button = (url: string) => (url ? { inline_keyboard: [[{ text: "🔗 Acompanhar Sessão", url }]] } : undefined);
const SEP = "─".repeat(20);

export const sendPlanTelegramUpdate = (t: TelegramNotifier, repo: string, id: string, url: string, plan: string, decision: string) =>
  t.sendMessage(["📋 <b>JULES TRACKER — REVISÃO DE PLANO</b>", `🏢 <b>Repositório:</b> <code>${esc(repo)}</code>`, `🆔 <b>Sessão:</b> <code>${esc(id)}</code>`, SEP, `📝 <b>Plano:</b>\n${esc(plan.slice(0, 1000))}`, SEP, `🤖 <b>Decisão (AI):</b> ${esc(decision)}`].join("\n"), "HTML", button(url));

export const sendTelegramUpdate = (t: TelegramNotifier, repo: string, id: string, url: string, question: string, answer: string) =>
  t.sendMessage(["🔍 <b>JULES TRACKER UPDATE</b>", `🏢 <b>Repositório:</b> <code>${esc(repo)}</code>`, `🆔 <b>Sessão:</b> <code>${esc(id)}</code>`, SEP, `❓ <b>Pergunta do Jules:</b>\n${esc(question)}`, SEP, `🤖 <b>Resposta sugerida (AI):</b>\n${esc(answer)}`].join("\n"), "HTML", button(url));
