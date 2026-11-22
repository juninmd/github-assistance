/** Composite agent: one scoped agent that runs former agents as ordered stages (each isolated, each still testable). */
import { join } from "node:path";
import { BaseAgent } from "../base-agent.ts";
import type { AgentOpts } from "../agent-types.ts";
import { AGENTS_BY_NAME, type StageSpec } from "../catalog.ts";
import { agentDir } from "./utils.ts";

type Result = Record<string, any>;
const failed = (r: Result) => "error" in r || r.status === "failed";
const truthy = (v: string | undefined, d: boolean) => (v === undefined || v.trim() === "" ? d : ["1", "true", "yes", "on"].includes(v.trim().toLowerCase()));

export abstract class CompositeAgent extends BaseAgent {
  readonly stages: StageSpec[];
  /** Set when a former agent name was used: only that stage runs and its result is returned unchanged. */
  readonly onlyStage: string | null;
  protected opts: AgentOpts;

  constructor(name: string, o: AgentOpts) {
    super(name, o);
    this.opts = o;
    this.stages = AGENTS_BY_NAME.get(name)?.stages ?? [];
    this.onlyStage = o.stage ?? null;
    if (this.onlyStage && !this.stages.some((s) => s.name === this.onlyStage)) throw new Error(`unknown stage '${this.onlyStage}' for ${name}`);
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  /** Extra constructor options for a stage (e.g. observe-only or draft PRs). */
  protected stageOptions(_stage: StageSpec): Record<string, any> { return {}; }
  /** Null to run the stage; otherwise the reason it is skipped (given the results of earlier stages). */
  protected skipReason(stage: StageSpec, _done: Record<string, Result>): string | null {
    if (stage.requiresAi && !this.opts.ai) return "ENABLE_AI=false";
    return truthy(stage.toggleEnv ? process.env[stage.toggleEnv] : undefined, true) ? null : `${stage.toggleEnv}=false`;
  }
  /** Hook after a stage finished (e.g. persist its results for a later run). */
  protected afterStage(_stage: StageSpec, _result: Result): void {}

  async createStage(stage: StageSpec): Promise<BaseAgent> {
    const mod = await import(join(agentDir(stage.dir), "agent.ts"));
    const Cls = mod[stage.className];
    if (!Cls) throw new Error(`${stage.className} not exported by agents/${stage.dir}/agent.ts`);
    const { stage: _omit, ...base } = this.opts;
    return new Cls({ ...base, ...this.stageOptions(stage) });
  }

  private async runStage(stage: StageSpec): Promise<Result> {
    try { const r = (await (await this.createStage(stage)).run()) ?? {}; this.afterStage(stage, r); return r; }
    catch (e: any) { this.log(`Stage ${stage.name} failed: ${e?.message ?? e}`, "ERROR"); return { error: String(e?.message ?? e) }; }
  }

  async run(): Promise<Result> {
    if (this.onlyStage) return this.runStage(this.stages.find((s) => s.name === this.onlyStage)!);
    const done: Record<string, Result> = {}, skipped: Record<string, string> = {};
    for (const stage of this.stages) {
      const reason = this.skipReason(stage, done);
      if (reason) { skipped[stage.name] = reason; this.log(`Stage ${stage.name} skipped: ${reason}`); continue; }
      done[stage.name] = await this.runStage(stage);
    }
    const out: Result = { agent: this.name, stages: done, skipped_stages: skipped };
    const bad = Object.entries(done).filter(([, r]) => failed(r)).map(([n]) => n);
    if (bad.length) out.error = `stage(s) failed: ${bad.join(", ")}`;
    return out;
  }
}
