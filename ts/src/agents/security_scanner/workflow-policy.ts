/**
 * GitHub Actions workflow policy: scheduled (cron) workflows are prohibited (they burn runner minutes on idle repos).
 * Line-based scan (no YAML dependency): `cron:` only appears under `schedule:` in Actions workflows.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export const WORKFLOW_DIR = ".github/workflows";
/** The one sanctioned scheduled workflow: the portfolio orchestrator entry point. */
export const APPROVED_SCHEDULED_WORKFLOWS = new Set(["daily-project-creator.yml"]);
const CRON_LINE = /^\s*-?\s*cron\s*:\s*(.+?)\s*$/i;
export type CronViolation = { file: string; line: number; cron: string };

function cleanExpr(raw: string): string {
  let e = raw.trim();
  const q = e[0];
  if (q === '"' || q === "'") {
    const close = e.indexOf(q, 1);
    if (close !== -1) return e.slice(1, close).trim();
    e = e.slice(1);
  } else if (e.includes("#")) e = e.split("#", 1)[0].trim();
  return e;
}

export function scanWorkflowText(text: string, file = ""): CronViolation[] {
  const out: CronViolation[] = [];
  text.split(/\r?\n/).forEach((line, i) => { const m = CRON_LINE.exec(line); if (m) out.push({ file, line: i + 1, cron: cleanExpr(m[1]) }); });
  return out;
}

export function detectCronWorkflows(repoDir: string, approved: ReadonlySet<string> = APPROVED_SCHEDULED_WORKFLOWS): CronViolation[] {
  const dir = join(repoDir, WORKFLOW_DIR);
  if (!existsSync(dir) || !statSync(dir).isDirectory()) return [];
  const out: CronViolation[] = [];
  for (const name of readdirSync(dir)) {
    if (!/\.ya?ml$/.test(name) || approved.has(name)) continue;
    const p = join(dir, name);
    try { if (!statSync(p).isFile()) continue; out.push(...scanWorkflowText(readFileSync(p, "utf8"), `${WORKFLOW_DIR}/${name}`)); } catch { /* unreadable */ }
  }
  return out.sort((a, b) => (a.file < b.file ? -1 : a.file > b.file ? 1 : 0) || a.line - b.line);
}
