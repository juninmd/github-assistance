/** Secret Guard - scan the portfolio, classify findings, rewrite history only after the owner's explicit approval. */
import type { AgentOpts } from "../agent-types.ts";
import type { StageSpec } from "../catalog.ts";
import { CompositeAgent } from "../core/composite.ts";
import { saveResults } from "../core/reporting.ts";

type Result = Record<string, any>;

export class SecretGuardAgent extends CompositeAgent {
  private scan: Result | null = null;
  constructor(o: AgentOpts) { super("secret-guard", o); }

  protected skipReason(stage: StageSpec, done: Record<string, Result>): string | null {
    if (stage.name === "remove" && done.scan && ("error" in done.scan || done.scan.status === "failed")) return "scan failed";
    return super.skipReason(stage, done);
  }
  protected stageOptions(stage: StageSpec) { return stage.name === "remove" && this.scan ? { scanResults: this.scan } : {}; }
  protected afterStage(stage: StageSpec, r: Result): void {
    if (stage.name !== "scan" || "error" in r) return;
    this.scan = r;
    // Keeps `run-agent secret-remover` (former name) working from the latest scan file.
    try { saveResults("security-scanner", r); } catch (e: any) { this.log(`could not save scan results: ${e?.message ?? e}`, "WARNING"); }
  }
}
