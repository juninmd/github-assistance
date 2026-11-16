/** Content-level credential detection used as a push guard for agent PRs. Findings never include the secret. */
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { run } from "./proc.ts";
import { DEFAULT_ENV_DENY, WILDCARD } from "./secure-git.ts";
import { sastScan } from "./sast-scan.ts";

const MAX_FILE_BYTES = 4 * 1024 * 1024;
export type Finding = { file?: string; rule_id: string; line: number };

export const SECRET_PATTERNS: [string, RegExp][] = [
  ["github-pat", /gh[pousr]_[A-Za-z0-9]{20,}/],
  ["github-fine-grained", /github_pat_[A-Za-z0-9_]{22,}/],
  ["jules-key", /AQ\.Ab8[A-Za-z0-9]{20,}/],
  ["openai-style", /sk-[A-Za-z0-9]{20,}/],
  ["google-api-key", /AIza[0-9A-Za-z_-]{35}/],
  ["slack-token", /xox[bapr]-[A-Za-z0-9-]{18,}/],
  ["private-key", /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ["url-embedded-github-cred", /(?:https?|git\+https?):\/\/[^/\s:@[\]<>'"]{15,}@github\.com/],
];

export function knownSecrets(env: Record<string, string | undefined> = process.env): string[] {
  return Object.entries(env)
    .filter(([n]) => DEFAULT_ENV_DENY.includes(n) || WILDCARD.test(n))
    .map(([, v]) => v ?? "")
    .filter((v) => v.length >= 20 && !v.startsWith("http"));
}

export function scanText(text: string, o: { known?: string[]; env?: Record<string, string | undefined> } = {}): Finding[] {
  const out: Finding[] = [], seen = new Set<string>();
  const lines = text.split(/\r?\n/);
  const add = (rule_id: string, line: number) => { const k = `${rule_id}:${line}`; if (!seen.has(k)) { seen.add(k); out.push({ rule_id, line }); } };
  for (const s of o.known ?? knownSecrets(o.env)) {
    if (!text.includes(s)) continue;
    add("known-secret", lines.findIndex((l) => l.includes(s)) + 1);
  }
  for (const [id, re] of SECRET_PATTERNS) lines.forEach((l, i) => { if (re.test(l)) add(id, i + 1); });
  return out;
}

export const gitleaksEnabled = () => !["off", "0", "false", "no"].includes((process.env.PUSH_GUARD_GITLEAKS ?? "auto").toLowerCase()) && !!Bun.which("gitleaks");
export function gitleaksConfig(): string | null {
  const p = process.env.GITLEAKS_CONFIG || resolve(import.meta.dir, "../../../config/gitleaks.toml");
  return existsSync(p) ? p : null;
}

/** Fail-open: tool errors return no findings (the regex layer still guards). */
export async function gitleaksScan(cloneDir: string): Promise<Finding[]> {
  const root = resolve(cloneDir), tmp = mkdtempSync(join(tmpdir(), "gl-")), report = join(tmp, "report.json");
  try {
    const cmd = ["gitleaks", "detect", "--no-git", "--source", root, "--redact", "--no-banner", "--report-format", "json", "--report-path", report];
    const cfg = gitleaksConfig();
    if (cfg) cmd.push("--config", cfg);
    const r = await run(cmd, { timeoutMs: 180_000 });
    if (r.code !== 1 || !existsSync(report)) return [];
    const raw = JSON.parse(readFileSync(report, "utf8") || "[]");
    return (Array.isArray(raw) ? raw : []).map((i: any) => {
      let file = String(i.File ?? "");
      try { const rel = relative(root, resolve(file)); if (!rel.startsWith("..")) file = rel; } catch { /* keep */ }
      return { file: file.replace(/\\/g, "/"), rule_id: `gitleaks:${i.RuleID ?? "unknown"}`, line: Number(i.StartLine ?? 0) };
    });
  } catch { return []; } finally { rmSync(tmp, { recursive: true, force: true }); }
}

function walk(dir: string, root: string, out: string[]): void {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name === ".git") continue;
    const p = join(dir, e.name);
    e.isDirectory() ? walk(p, root, out) : e.isFile() && out.push(p);
  }
}

function scanRegex(root: string, known?: string[], env?: Record<string, string | undefined>): Finding[] {
  const resolved = known ?? knownSecrets(env), files: string[] = [], out: Finding[] = [];
  walk(root, root, files);
  for (const f of files.sort()) {
    try {
      if (statSync(f).size > MAX_FILE_BYTES) continue;
      for (const h of scanText(readFileSync(f, "utf8"), { known: resolved })) out.push({ file: relative(root, f).replace(/\\/g, "/"), ...h });
    } catch { /* unreadable */ }
  }
  return out;
}

/** Scan a clone's working tree: regex + gitleaks + SAST, de-duplicated by file+line. */
export async function scanClone(cloneDir: string, o: { known?: string[]; env?: Record<string, string | undefined> } = {}): Promise<Finding[]> {
  if (!existsSync(cloneDir) || !statSync(cloneDir).isDirectory()) return [];
  const root = resolve(cloneDir), found = scanRegex(root, o.known, o.env);
  const merge = (more: Finding[]) => { const seen = new Set(found.map((f) => `${f.file}:${f.line}`)); found.push(...more.filter((f) => !seen.has(`${f.file}:${f.line}`))); };
  if (gitleaksEnabled()) merge(await gitleaksScan(root));
  merge(await sastScan(root));
  return found;
}

export function redactText(text?: string | null, o: { known?: string[]; env?: Record<string, string | undefined> } = {}): string {
  let r = text ?? "";
  for (const s of o.known ?? knownSecrets(o.env)) r = r.split(s).join("[REDACTED]");
  for (const [, re] of SECRET_PATTERNS) r = r.replace(new RegExp(re.source, "g"), "[REDACTED]");
  return r;
}
