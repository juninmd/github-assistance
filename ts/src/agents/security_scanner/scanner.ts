/** Gitleaks scanning helpers for the Security Scanner agent. */
import { existsSync, mkdtempSync, readFileSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve, sep } from "node:path";
import { run } from "../../utils/proc.ts";
import { authConfigArgs, githubCloneUrl } from "../../utils/secure-git.ts";
import { detectCronWorkflows } from "./workflow-policy.ts";

type Log = (m: string, level?: string) => void;

export async function ensureGitleaksInstalled(log: Log): Promise<boolean> {
  try {
    const r = await run(["gitleaks", "version"], { timeoutMs: 10_000 });
    if (r.code === 0) { log(`Gitleaks is installed: ${r.stdout.trim()}`); return true; }
  } catch { /* not installed */ }
  log("Gitleaks not found in PATH.");
  if (process.platform !== "linux" && process.platform !== "darwin") { log("Auto-install for gitleaks is only supported on Linux. Please install it manually.", "WARNING"); return false; }
  log("Attempting to install gitleaks (Linux)...");
  try {
    const script = "cd /tmp && wget -q https://github.com/gitleaks/gitleaks/releases/download/v8.18.1/gitleaks_8.18.1_linux_x64.tar.gz && tar xzf gitleaks_8.18.1_linux_x64.tar.gz && chmod +x gitleaks && cp gitleaks /tmp/gitleaks_bin";
    const r = await run(["sh", "-c", script], { timeoutMs: 60_000 });
    if (r.code === 0) { log("Gitleaks downloaded to /tmp/gitleaks_bin"); return true; }
    log(`Failed to install gitleaks: ${r.stderr}`, "ERROR"); return false;
  } catch (e: any) { log(`Error installing gitleaks: ${e?.name} - ${e?.message ?? e}`, "ERROR"); return false; }
}

/** Only safe metadata — NEVER Secret, Match or any credential data. */
export const sanitizeFindings = (findings: Record<string, any>[]) => findings.map((f) => ({
  rule_id: f.RuleID ?? "unknown", description: f.Description ?? "", file: f.File ?? "", line: f.StartLine ?? 0,
  commit: (f.Commit ?? "").slice(0, 8), full_commit: f.Commit ?? "", author: f.Author ?? "", date: f.Date ?? "",
}));

function stripClonePrefix(findings: Record<string, any>[], cloneDir: string) {
  const root = realpathSync(cloneDir);
  for (const f of findings) {
    if (!("File" in f)) continue;
    const abs = resolve(f.File);
    if (abs === root || abs.startsWith(root + sep)) f.File = relative(root, abs);
  }
}

export async function scanRepository(repo: string, defaultBranch: string, log: Log) {
  log(`Scanning repository: ${repo}`);
  const result: Record<string, any> = { repository: repo, default_branch: defaultBranch, findings: [], cron_workflows: [], error: null, scanned: false };
  const token = process.env.GITHUB_TOKEN;
  if (!token) { result.error = "GITHUB_TOKEN not available"; return result; }
  const tmp = mkdtempSync(join(tmpdir(), "scan-"));
  try {
    const cloneDir = join(tmp, "repo");
    log(`Cloning ${repo} (full history)...`);
    const c = await run(["git", ...authConfigArgs(token), "clone", "--single-branch", githubCloneUrl(repo), cloneDir], { timeoutMs: 600_000 });
    if (c.timedOut) { result.error = "Scan timeout exceeded"; return result; }
    if (c.code !== 0) { result.error = `Clone failed with exit code ${c.code}`; return result; }
    // Policy check: prohibited cron workflows surface in the same sweep; never abort the scan.
    try {
      const cron = detectCronWorkflows(cloneDir); result.cron_workflows = cron;
      if (cron.length) log(`${repo}: ${cron.length} prohibited cron workflow trigger(s) detected`, "WARNING");
    } catch (e: any) { log(`Cron workflow check failed for ${repo}: ${e?.message ?? e}`, "WARNING"); }
    const report = join(tmp, "gitleaks-report.json");
    log(`Running gitleaks scan on ${repo}...`);
    const g = await run(["gitleaks", "detect", "--source", cloneDir, "--report-path", report, "--report-format", "json"], { timeoutMs: 300_000 });
    if (g.timedOut) { result.error = "Scan timeout exceeded"; return result; }
    if (g.code !== 0 && g.code !== 1) { result.error = `Gitleaks scan failed with exit code ${g.code}`; return result; }
    if (existsSync(report)) {
      try { const findings = JSON.parse(readFileSync(report, "utf8")); stripClonePrefix(findings, cloneDir); result.findings = sanitizeFindings(findings); }
      catch (e: any) { result.error = `Failed to parse gitleaks report: ${e?.message ?? e}`; return result; }
    }
    result.scanned = true;
    log(`Scan completed for ${repo}: ${result.findings.length} findings`);
  } catch (e: any) {
    result.error = e?.code === "ENOENT" ? "Executable not found (gitleaks or git)" : `Scan error: ${e?.message ?? e}`;
    log(`Error scanning ${repo}: ${e?.message ?? e}`, "ERROR");
  } finally { rmSync(tmp, { recursive: true, force: true }); }
  return result;
}
