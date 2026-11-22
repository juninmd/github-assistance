/** Agent metrics: processed/failed counts, duration, LLM usage delta; appends to the cost ledger. */
import { usage } from "../../ai/usage.ts";
import { recordRun } from "../../insight/cost.ts";

export class AgentMetrics {
  start = new Date();
  private usageStart = usage.snapshot();
  metrics: Record<string, any>;
  constructor(public agentName: string) {
    this.metrics = { agent_name: agentName, execution_start: this.start.toISOString(), items_processed: 0, items_failed: 0, github_api_calls: 0, errors: [], warnings: [] };
  }
  incrementProcessed(n = 1) { this.metrics.items_processed += n; }
  incrementFailed(n = 1) { this.metrics.items_failed += n; }
  recordGithubApiCall() { this.metrics.github_api_calls++; }
  addError(message: string) { this.metrics.errors.push({ timestamp: new Date().toISOString(), message }); }
  addWarning(message: string) { this.metrics.warnings.push({ timestamp: new Date().toISOString(), message }); }
  finalize() {
    const end = new Date(), m = this.metrics;
    const total = m.items_processed + m.items_failed;
    Object.assign(m, usage.delta(this.usageStart), {
      execution_end: end.toISOString(), duration_seconds: (end.getTime() - this.start.getTime()) / 1000,
      success_rate: Math.round((total ? (m.items_processed / total) * 100 : 100) * 100) / 100,
      total_items: total, error_count: m.errors.length, warning_count: m.warnings.length,
    });
    recordRun(m);
    return m;
  }
  summary(): string {
    const m = this.metrics, total = m.items_processed + m.items_failed;
    const rate = total ? (m.items_processed / total) * 100 : 100;
    const lines = [`📊 Agent Metrics Summary: ${this.agentName}`, `⏱️  Duration: ${((Date.now() - this.start.getTime()) / 1000).toFixed(2)}s`, `✅ Processed: ${m.items_processed}`, `❌ Failed: ${m.items_failed}`, `📈 Success Rate: ${rate.toFixed(0)}%`, `🔗 GitHub API Calls: ${m.github_api_calls}`];
    if (m.errors.length) lines.push(`⚠️  Errors: ${m.errors.length}`);
    if (m.warnings.length) lines.push(`⚠️  Warnings: ${m.warnings.length}`);
    return lines.join("\n");
  }
}
