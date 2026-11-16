/** Secret Remover - classifies scanner findings with AI and remediates (history rewrite or gitleaks allowlist). */
import { BaseAgent } from "../base-agent.ts";
import { makeAi, type AgentOpts } from "../agent-types.ts";
import { FindingProcessor } from "./processor.ts";
import { findLatestResults } from "./utils.ts";
import { sendErrorNotification } from "./telegram-summary.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

const RESULTS_GLOB = "results/security-scanner_*.json";
const MAX_FINDINGS_PER_RUN = 300; // guard against runaway AI calls

export class SecretRemoverAgent extends BaseAgent {
  processor: FindingProcessor;
  constructor(o: AgentOpts) {
    super("secret_remover", { ...o, enforceRepositoryAllowlist: false });
    const ai = { ...o.ai, provider: process.env.SECRET_REMOVER_AI_PROVIDER ?? o.ai?.provider, model: process.env.SECRET_REMOVER_AI_MODEL ?? o.ai?.model };
    this.processor = new FindingProcessor(o.aiClient ?? makeAi(ai).client, this.telegram, this.githubClient, this.log);
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    this.log("Starting Secret Remover workflow");
    const latest = findLatestResults(this.log, RESULTS_GLOB);
    if (!latest) {
      const msg = "No security scanner results found in results/.";
      this.log(msg, "ERROR"); await sendErrorNotification(this.telegram, this.targetOwner, msg);
      return { error: msg };
    }
    const repos: any[] = latest.repositories_with_findings ?? [];
    this.log(`Processing ${repos.length} repositories with findings`);
    const actions: any[] = [], errors: any[] = [];
    let count = 0;
    for (const rd of repos) {
      if (count >= MAX_FINDINGS_PER_RUN) { this.log(`Reached max findings limit (${MAX_FINDINGS_PER_RUN}), stopping`); break; }
      const findings = (rd.findings as any[]).slice(0, MAX_FINDINGS_PER_RUN - count);
      count += findings.length;
      try { actions.push(await this.processor.processRepo(rd.repository, findings, rd.default_branch ?? "main")); }
      catch (e: any) {
        this.log(`Error processing ${rd.repository}: ${e?.message ?? e}`, "ERROR");
        errors.push({ repository: rd.repository, error: String(e?.message ?? e) });
        const esc = TelegramNotifier.escapeHtml;
        await this.telegram.sendMessage(`❌ <b>SECRET REMOVER — ERRO</b>\n──────────────────────\n📦 <b>Repo:</b> <code>${esc(rd.repository)}</code>\n<pre>${esc(String(e?.message ?? e).slice(0, 300))}</pre>`, "HTML");
      }
    }
    return { total_repos_processed: repos.length, actions_taken: actions, errors, timestamp: new Date().toISOString() };
  }
}
