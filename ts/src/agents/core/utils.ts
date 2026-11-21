/** Utilities shared by agents (PR bodies, instructions, labels, owner assignment, git config). */
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { DEFAULT_LITELLM_API_BASE } from "../../config/settings.ts";
import { run } from "../../utils/proc.ts";
import type { GithubClient, PR } from "../../github/client.ts";

type Log = (msg: string, level?: string) => void;

export function buildOriginMetadata(agentName: string, model = "opencode"): string {
  return `---\n🤖 **Origem Automatizada**\n- **Agente:** \`${agentName}\`\n- **Modelo:** \`${model}\`\n- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)`;
}
export function buildPrBody(agentName: string, title: string, opencodeOutput: string, model = "opencode"): string {
  return `## 🤖 Alterações aplicadas automaticamente\n\n### O que foi feito\n${title}\n\n### Saída do opencode\n\`\`\`\n${opencodeOutput.slice(0, 1500)}\n\`\`\`\n\n### Evidências\n<!-- Anexe prints (antes/depois), saída de testes ou logs que provem a mudança. -->\n\n${buildOriginMetadata(agentName, model)}`;
}

export const EXECUTION_POLICY_BLOCK = `
# EXECUTION POLICY (mandatory)
- GitHub Actions execution is PROHIBITED. Never create, modify, or reference
  any GitHub Actions workflow (\`.github/workflows/\`, \`on: schedule:\`, \`cron:\`).
- All periodic and event-driven work runs on the Kubernetes cluster
  (CronJobs/Jobs). If a task needs scheduling, delegate it to the central
  cluster orchestrator — never add \`cron\` or \`schedule\` triggers.
- All AI usage goes through the OpenAI-compatible LiteLLM proxy
  (\`${DEFAULT_LITELLM_API_BASE}\`). Do not use other providers.
`;

/** Agent assets (instructions.md, templates) live in src/agents/<package>/ next to the code. */
export const agentDir = (agentName: string) => resolve(import.meta.dir, "..", agentName.replace(/-/g, "_"));
function readOr(file: string, log?: Log, level = "WARNING", what = "file"): string | null {
  if (!existsSync(file)) { log?.(`${what} not found: ${file}`, level); return null; }
  try { return readFileSync(file, "utf8"); } catch (e: any) { log?.(`Error loading ${what}: ${e?.message ?? e}`, "ERROR"); return null; }
}
export const loadInstructions = (agentName: string, log?: Log) => readOr(join(agentDir(agentName), "instructions.md"), log, "WARNING", "Instructions file") ?? "";
export function loadJulesInstructions(agentName: string, templateName = "jules-instructions.md", variables?: Record<string, unknown>, log?: Log): string {
  let t = readOr(join(agentDir(agentName), templateName), log, "ERROR", "Jules instructions template");
  if (t === null) return "";
  for (const [k, v] of Object.entries(variables ?? {})) t = t.split(`{{${k}}}`).join(String(v));
  return t + EXECUTION_POLICY_BLOCK;
}
export function getInstructionsSection(instructions: string, header: string): string {
  if (!instructions) return "";
  const out: string[] = []; let inSection = false, level = 0;
  for (const line of instructions.split("\n")) {
    const s = line.trim();
    if (s.startsWith("#") && s.toLowerCase().includes(header.toLowerCase()) && !inSection) { inSection = true; level = line.split(/\s+/)[0].length; continue; }
    if (inSection) { if (s.startsWith("#") && line.split(/\s+/)[0].length <= level) break; out.push(line); }
  }
  return out.join("\n").trim();
}

export async function checkGithubRateLimit(gh: GithubClient, log?: Log): Promise<number> {
  try {
    const { rate } = await gh.get("/rate_limit");
    const pct = rate.limit ? (rate.remaining / rate.limit) * 100 : 0;
    if (pct < 10) log?.(`⚠️ GitHub API rate limit critical: ${rate.remaining}/${rate.limit} (${pct.toFixed(0)}%)`, "WARNING");
    else if (pct < 25) log?.(`GitHub API rate limit low: ${rate.remaining}/${rate.limit} (${pct.toFixed(0)}%)`, "WARNING");
    return rate.remaining;
  } catch (e: any) { log?.(`Could not check rate limit: ${e?.message ?? e}`, "WARNING"); return -1; }
}

export const extractSessionDatetime = (s: Record<string, any>): Date | null => {
  const v = s.createTime || s.createdAt; if (!v) return null;
  const d = new Date(v); return Number.isNaN(d.getTime()) ? null : d;
};
/** True when the session was created on `target` (YYYY-MM-DD) in UTC-3. */
export function isSameDayUtcMinus3(s: Record<string, any>, target: string | null | undefined): boolean {
  const d = extractSessionDatetime(s);
  return !!d && !!target && new Date(d.getTime() - 3 * 3600_000).toISOString().slice(0, 10) === target;
}

export async function hasRecentJulesSession(jules: { listSessions(o?: any): Promise<any[]> }, repository: string, taskKeyword = "", hours = 24, log?: Log): Promise<boolean> {
  try {
    const cutoff = Date.now() - hours * 3600_000;
    for (const s of await jules.listSessions({ pageSize: 100 })) {
      const dt = extractSessionDatetime(s);
      if (!dt || dt.getTime() < cutoff) continue;
      const title = (s.title ?? "").toLowerCase();
      if (title.includes(repository.toLowerCase()) && (!taskKeyword || title.includes(taskKeyword.toLowerCase()))) {
        log?.(`Skipping duplicate: recent session found for ${repository} (${taskKeyword})`);
        return true;
      }
    }
    return false;
  } catch (e: any) { log?.(`Could not check recent sessions: ${e?.message ?? e}`, "WARNING"); return false; }
}

export const ROADMAP_LABEL = "roadmap", ROADMAP_ACTIVE_LABEL = "jules";

/** Create a repository label if missing (case-insensitive). Best-effort. */
export async function ensureLabel(gh: GithubClient, repo: string, name: string, color: string, description = "", log?: Log): Promise<void> {
  try {
    const existing = new Set((await gh.paginate<any>(`/repos/${repo}/labels`)).map((l) => l.name.toLowerCase()));
    if (!existing.has(name.toLowerCase())) await gh.post(`/repos/${repo}/labels`, { name, color, description });
  } catch (e: any) { log?.(`Could not ensure label '${name}': ${e?.message ?? e}`, "WARNING"); }
}

const owner = () => process.env.GITHUB_OWNER ?? "juninmd";
/** Assign an issue/PR to the owner; best-effort, never throws. */
export async function assignOwner(gh: GithubClient, item: PR, login?: string | null, log?: Log): Promise<boolean> {
  const who = login || owner();
  try {
    if ((item.assignees ?? []).some((a: any) => (a.login ?? "").toLowerCase() === who.toLowerCase())) return true;
    const [ok, msg] = await gh.addAssigneeToPr(item, who);
    if (!ok) throw new Error(msg);
    return true;
  } catch (e: any) { log?.(`Could not assign '${who}': ${e?.message ?? e}`, "WARNING"); return false; }
}
/** Request review from the owner unless they authored the PR or are already requested. Never throws. */
export async function requestReviewOwner(gh: GithubClient, item: PR, login?: string | null, log?: Log): Promise<boolean> {
  const who = login || owner();
  try {
    if (typeof item.user?.login === "string" && item.user.login.toLowerCase() === who.toLowerCase()) return false;
    if ((item.requested_reviewers ?? []).some((r: any) => typeof r.login === "string" && r.login.toLowerCase() === who.toLowerCase())) return true;
    const [ok, msg] = await gh.requestReviewerOnPr(item, who);
    if (!ok) throw new Error(msg);
    return true;
  } catch (e: any) { log?.(`Could not request review from '${who}': ${e?.message ?? e}`, "WARNING"); return false; }
}
/** Order-preserving map with at most `limit` calls in flight. */
export async function mapLimit<T, R>(items: readonly T[], limit: number, fn: (item: T, i: number) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(items.length);
  let next = 0;
  const worker = async () => { for (let i = next++; i < items.length; i = next++) out[i] = await fn(items[i]!, i); };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return out;
}
export const issueHasLabel = (issue: PR, name: string) => (issue.labels ?? []).some((l: any) => (typeof l === "string" ? l : l.name).toLowerCase() === name.toLowerCase());

export async function setupGitConfig(dir: string): Promise<void> {
  await run(["git", "config", "user.email", "github-assistance@github.com"], { cwd: dir });
  await run(["git", "config", "user.name", "github-assistance"], { cwd: dir });
}
export const DEFAULT_OPENCODE_MODEL = () => process.env.OPENCODE_MODEL ?? "litellm/cloud/auto";
