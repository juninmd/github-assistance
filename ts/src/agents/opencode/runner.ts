/** OpenCode runner for agent-based repository automation (clone, run, guard, push, PR, audit). */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomInt } from "node:crypto";
import { semanticMessage } from "../core/commit-message.ts";
import { assignOwner, buildPrBody, requestReviewOwner, setupGitConfig } from "../core/utils.ts";
import { PREFERRED_FREE_MODEL, nextModel } from "./models.ts";
import * as tokenix from "../../utils/tokenix.ts";
import { run, type RunResult } from "../../utils/proc.ts";
import { redactText, scanClone } from "../../utils/secret-scan.ts";
import { authConfigArgs, githubCloneUrl, scrubEnv } from "../../utils/secure-git.ts";
import type { RepositoryAllowlist } from "../../config/allowlist.ts";
import type { GithubClient } from "../../github/client.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";
import { ensureContract } from "../core/agent-contract.ts";
import { createAgentPull, DEFAULT_PR_OPTIONS, type PrOptions } from "../core/pr-options.ts";

type Log = (m: string, level?: string) => void;
const envInt = (n: string, d: number, min = 1) => { const v = parseInt(process.env[n] ?? "", 10); return Number.isNaN(v) ? d : Math.max(min, v); };
const FALLBACK = "opencode/big-pickle";
const shuffle = <T>(xs: T[]) => { const a = [...xs]; for (let i = a.length - 1; i > 0; i--) { const j = randomInt(i + 1); [a[i], a[j]] = [a[j], a[i]]; } return a; };

export class OpencodeRunner {
  static modelCache: string | null = null;
  static modelsCache: string[] | null = null;
  modelsTimeout = envInt("OPENCODE_MODELS_TIMEOUT_SECONDS", 20); cloneTimeout = envInt("OPENCODE_CLONE_TIMEOUT_SECONDS", 120);
  warmupTimeout = envInt("OPENCODE_WARMUP_TIMEOUT_SECONDS", 180); runTimeout = envInt("OPENCODE_RUN_TIMEOUT_SECONDS", 1200);
  pushTimeout = envInt("OPENCODE_PUSH_TIMEOUT_SECONDS", 120); maxAttempts = envInt("OPENCODE_RUN_MAX_ATTEMPTS", 3);
  telegram: TelegramNotifier;
  constructor(private allowlist: RepositoryAllowlist, private log: Log, private gh: GithubClient, telegram?: TelegramNotifier | null, private targetOwner?: string | null) { this.telegram = telegram ?? new TelegramNotifier(); }

  async getFreeOpencodeModels(): Promise<string[]> {
    if (OpencodeRunner.modelsCache === null) {
      const r = await run(["opencode", "models"], { timeoutMs: this.modelsTimeout * 1000 });
      if (r.code !== 0) { this.log(`opencode models failed (rc=${r.code}): ${r.stderr}`, "WARNING"); OpencodeRunner.modelsCache = [FALLBACK]; }
      else {
        const free = r.stdout.split("\n").map((m) => m.trim()).filter((m) => m && (m.endsWith("-free") || m === FALLBACK));
        OpencodeRunner.modelsCache = free.length ? free : [FALLBACK];
      }
    }
    const models = [...OpencodeRunner.modelsCache];
    return models.includes(PREFERRED_FREE_MODEL) ? [PREFERRED_FREE_MODEL, ...shuffle(models.filter((m) => m !== PREFERRED_FREE_MODEL))] : shuffle(models);
  }
  async getRandomFreeOpencodeModel(): Promise<string> {
    if (OpencodeRunner.modelCache !== null) return OpencodeRunner.modelCache;
    const models = await this.getFreeOpencodeModels(), chosen = models[randomInt(models.length)];
    this.log(`Selected free opencode model: ${chosen}`); return chosen;
  }
  async getPreferredOrRandomFreeOpencodeModel(): Promise<string> {
    if (OpencodeRunner.modelCache !== null) return OpencodeRunner.modelCache;
    const chosen = (await this.getFreeOpencodeModels())[0] ?? FALLBACK;
    this.log(`Selected free opencode model: ${chosen}`); return chosen;
  }

  /** Run with scrubbed env and timeout; returns [result, error]. */
  async safeRun(cmd: string[], timeoutSeconds: number, cwd?: string): Promise<[RunResult | null, string | null]> {
    const env = scrubEnv(); env.NODE_OPTIONS ??= "--max-old-space-size=2048"; env.NODE_ENV ??= "production";
    const r = await run(cmd, { cwd, env, timeoutMs: timeoutSeconds * 1000 });
    if (r.timedOut) return [null, `Command timed out after ${timeoutSeconds}s: ${cmd.join(" ")}`];
    if (r.code === 127 && /ENOENT|not found|No such file/i.test(r.stderr)) return [null, `Command not found: ${cmd[0]}`];
    return [r, null];
  }

  private audit(emoji: string, status: string, repository: string, title: string, detail = ""): Promise<boolean> {
    let text = `${emoji} <b>github-assistance audit</b>\n──────────────────────\n📦 <b>Repo:</b> <code>${repository}</code>\n🏷 <b>Tarefa:</b> ${title}\n📊 <b>Status:</b> <code>${status}</code>`;
    if (detail) text += `\n⚠️ <pre>${detail.slice(0, 300)}</pre>`;
    return this.telegram.sendMessage(text);
  }

  async runOnRepo(repository: string, instructions: string, title: string, agentName = "agent", prOptions: PrOptions = DEFAULT_PR_OPTIONS): Promise<Record<string, any>> {
    if (!this.allowlist.isAllowed(repository)) throw new Error(`opencode denied: Repository ${repository} is not in allowlist`);
    const model = await this.getPreferredOrRandomFreeOpencodeModel();
    const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 12);
    const branch = "agent/" + title.toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 60) + "-" + stamp;
    await this.audit("🚀", "iniciando", repository, title);
    await ensureContract(this.log);
    const tmp = mkdtempSync(join(tmpdir(), "oc-"));
    let runResult: RunResult | null = null, usedModel = model;
    try {
      const [clone, cloneErr] = await this.safeRun(["git", ...authConfigArgs(), "clone", "--depth=1", githubCloneUrl(repository), tmp], this.cloneTimeout);
      const cloneFail = cloneErr ?? (clone && clone.code !== 0 ? clone.stderr : null);
      if (cloneFail !== null) { this.log(`[${title}] git clone failed: ${cloneFail}`, "ERROR"); await this.audit("❌", "clone_failed", repository, title, cloneFail.slice(0, 300)); return { status: "clone_failed", error: cloneFail.slice(0, 300) }; }
      await setupGitConfig(tmp);
      await run(["git", "checkout", "-b", branch], { cwd: tmp });
      const outcome = await tokenix.session(tmp, async () => {
        this.log(`[${title}] Warming up opencode...`);
        const [, warmErr] = await this.safeRun(["opencode", "run", "--model", model, "ping"], this.warmupTimeout, tmp);
        if (warmErr) this.log(`[${title}] warmup skipped: ${warmErr}`, "WARNING");
        let lastStatus = "opencode_failed", lastError = "Unknown opencode error";
        const free = await this.getFreeOpencodeModels();
        for (let attempt = 0; attempt < this.maxAttempts; attempt++) {
          // free first, another free next, cloud/auto (LiteLLM) only as the last resort
          const current = OpencodeRunner.modelCache ?? nextModel(free, model, attempt);
          this.log(`[${title}] Running opencode on ${repository} (attempt ${attempt + 1}/${this.maxAttempts}; model: ${current})...`);
          const [res, err] = await this.safeRun(["opencode", "run", "--model", current, instructions], this.runTimeout, tmp);
          if (err) { lastError = err; lastStatus = err.startsWith("Command timed out") ? "opencode_timeout" : "opencode_unavailable"; this.log(`[${title}] opencode execution error: ${err}`, "WARNING"); }
          else if (res && res.code === 0) { runResult = res; usedModel = current; break; }
          else { lastError = (res?.stderr || res?.stdout || `opencode returned exit code ${res?.code}`).slice(0, 300); lastStatus = "opencode_failed"; this.log(`[${title}] opencode failed (rc=${res?.code}): ${lastError}`, "WARNING"); }
        }
        if (!runResult) { await this.audit("❌", lastStatus, repository, title, lastError.slice(0, 300)); return { status: lastStatus, stderr: lastError.slice(0, 300), model: usedModel }; }
        await run(["git", "add", "-A"], { cwd: tmp });
        const findings = await scanClone(tmp);
        if (findings.length) {
          const detail = findings.slice(0, 8).map((h) => `${h.file}:${h.line} -> ${h.rule_id}`).join("; ");
          this.log(`[${title}] Push blocked: secret found in generated content: ${detail}`, "ERROR");
          await this.audit("⛔", "push_blocked_secret", repository, title, detail);
          return { status: "push_blocked_secret", findings: detail };
        }
        const commit = await run(["git", "commit", "-m", semanticMessage("feat", agentName, title, `Applied by github-assistance agent \`${agentName}\` via opencode (${usedModel}).`)], { cwd: tmp });
        if ((commit.stdout + commit.stderr).includes("nothing to commit")) { this.log(`[${title}] opencode made no changes.`); await this.audit("ℹ️", "no_changes", repository, title); return { status: "no_changes" }; }
        const [push, pushErr] = await this.safeRun(["git", ...authConfigArgs(), "push", "origin", branch], this.pushTimeout, tmp);
        const pushFail = pushErr ?? (push && push.code !== 0 ? push.stderr : null);
        if (pushFail !== null) { this.log(`[${title}] git push failed: ${pushFail}`, "ERROR"); await this.audit("❌", "push_failed", repository, title, pushFail.slice(0, 300)); return { status: "push_failed", error: pushFail.slice(0, 300) }; }
        return null;
      });
      if (outcome) return outcome;
    } finally { rmSync(tmp, { recursive: true, force: true }); }
    const prUrl = await this.openPullRequest(repository, branch, title, (runResult as RunResult | null)?.stdout ?? "", agentName, usedModel, prOptions);
    this.log(`[${title}] PR opened: ${prUrl}`);
    await this.audit("✅", "pr_aberto", repository, title, prUrl);
    return { status: "success", branch, pr_url: prUrl, model: usedModel, agent: agentName };
  }

  async openPullRequest(repository: string, branch: string, title: string, output: string, agentName = "agent", model = "opencode", prOptions: PrOptions = DEFAULT_PR_OPTIONS): Promise<string> {
    const repo = await this.gh.getRepo(repository);
    const pr = await createAgentPull(this.gh, repository, { title: `[agent/${agentName}] ${title}`, body: buildPrBody(agentName, title, redactText(output), model), head: branch, base: repo.default_branch }, prOptions, this.log);
    await assignOwner(this.gh, pr, this.targetOwner, this.log);
    await requestReviewOwner(this.gh, pr, this.targetOwner, this.log);
    return pr.html_url;
  }
}
