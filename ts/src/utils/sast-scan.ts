/** trufflehog / trivy / semgrep as extra push-guard layers. Fail-open; only findings in changed files block. */
import { mkdtempSync, readFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { run } from "./proc.ts";
import type { Finding } from "./secret-scan.ts";

export const TOOLS = ["trufflehog", "trivy", "semgrep"] as const;
const BLOCKING = new Set(["HIGH", "CRITICAL", "ERROR"]);
const TIMEOUT = 240_000;
type F = Required<Finding>;

export function selectedTools(): string[] {
  const mode = (process.env.PUSH_GUARD_SAST ?? "auto").trim().toLowerCase();
  if (["off", "0", "false", "no"].includes(mode)) return [];
  const wanted = mode === "auto" || mode === "" ? [...TOOLS] : mode.split(",").map((t) => t.trim());
  return wanted.filter((t) => (TOOLS as readonly string[]).includes(t) && Bun.which(t));
}

export async function changedFiles(root: string): Promise<Set<string> | null> {
  const r = await run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], { cwd: root, timeoutMs: 60_000 });
  if (r.code !== 0) return null;
  return new Set(r.stdout.split("\0").filter((e) => e.length > 3).map((e) => e.slice(3).trim()));
}

const rel = (p: string, root: string) => { const r = relative(resolve(root), resolve(p)); return (r.startsWith("..") ? p : r).replace(/\\/g, "/"); };

export function parseTrufflehog(raw: string, root: string): F[] {
  const out: F[] = [];
  for (const l of raw.split("\n")) {
    try {
      const d = JSON.parse(l), fs = d?.SourceMetadata?.Data?.Filesystem ?? {};
      if (d.DetectorName && fs.file) out.push({ file: rel(fs.file, root), line: Number(fs.line || 0), rule_id: `trufflehog:${d.DetectorName}` });
    } catch { /* skip */ }
  }
  return out;
}
export function parseTrivy(raw: string, root: string): F[] {
  const out: F[] = [];
  for (const res of JSON.parse(raw).Results ?? []) {
    const target = rel(String(res.Target ?? ""), root);
    for (const s of res.Secrets ?? []) out.push({ file: target, line: Number(s.StartLine || 0), rule_id: `trivy:${s.RuleID ?? "secret"}` });
    for (const [key, ident] of [["Misconfigurations", "ID"], ["Vulnerabilities", "VulnerabilityID"]] as const)
      for (const m of res[key] ?? []) if (BLOCKING.has(String(m.Severity ?? "").toUpperCase()))
        out.push({ file: target, line: Number(m.CauseMetadata?.StartLine || 0), rule_id: `trivy:${m[ident] ?? key}` });
  }
  return out;
}
export function parseSemgrep(raw: string, root: string): F[] {
  return (JSON.parse(raw).results ?? [])
    .filter((r: any) => BLOCKING.has(String(r.extra?.severity ?? "").toUpperCase()))
    .map((r: any) => ({ file: rel(String(r.path ?? ""), root), line: Number(r.start?.line || 0), rule_id: `semgrep:${r.check_id ?? "rule"}` }));
}

const RUNNERS: Record<string, { cmd: (root: string, targets: string[], report: string) => string[]; parse: (raw: string, root: string) => F[]; stdout: boolean }> = {
  trufflehog: { stdout: true, parse: parseTrufflehog, cmd: (root, t) => ["trufflehog", "filesystem", ...(t.length ? t : [root]), "--json", "--no-update", ...(["1", "true", "yes"].includes((process.env.PUSH_GUARD_TRUFFLEHOG_VERIFY ?? "").toLowerCase()) ? [] : ["--no-verification"])] },
  trivy: { stdout: false, parse: parseTrivy, cmd: (root, _t, report) => ["trivy", "fs", root, "--scanners", process.env.PUSH_GUARD_TRIVY_SCANNERS ?? "secret,misconfig", "--format", "json", "--output", report, "--quiet"] },
  semgrep: { stdout: false, parse: parseSemgrep, cmd: (root, t, report) => ["semgrep", "scan", "--config", process.env.PUSH_GUARD_SEMGREP_CONFIG ?? "p/security-audit", "--json", "--quiet", "--metrics=off", "--output", report, ...(t.length ? t : [root])] },
};

export async function runTool(name: string, root: string, targets: string[]): Promise<F[]> {
  const r = RUNNERS[name], tmp = mkdtempSync(join(tmpdir(), "sast-")), report = join(tmp, "report.json");
  try {
    const res = await run(r.cmd(root, targets, report), { cwd: root, timeoutMs: TIMEOUT });
    if (![0, 1].includes(res.code)) return [];
    const raw = r.stdout ? res.stdout : readFileSync(report, "utf8");
    return raw.trim() ? r.parse(raw, root) : [];
  } catch { return []; } finally { rmSync(tmp, { recursive: true, force: true }); }
}

/** `changedOverride` scans a fixed file set (a PR's files in a clean clone, where git status is empty). */
export async function sastScan(cloneDir: string, changedOverride?: Set<string>): Promise<F[]> {
  const root = resolve(cloneDir), tools = selectedTools();
  if (!tools.length) return [];
  const changed = changedOverride ?? (await changedFiles(root));
  const targets = [...(changed ?? [])].filter((f) => existsSync(join(root, f))).sort();
  if (changed && !targets.length) return [];
  let found: F[] = [];
  for (const t of tools) found.push(...(await runTool(t, root, ["semgrep", "trufflehog"].includes(t) ? targets : [])));
  if (changed) found = found.filter((f) => changed.has(f.file));
  return found;
}
