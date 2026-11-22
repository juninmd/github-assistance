/** Builder - plans (roadmap/issues) and implements improvements; every PR stays draft and is never merged by the bot. */
import type { AgentOpts } from "../agent-types.ts";
import { CompositeAgent } from "../core/composite.ts";
import { KEEP_DRAFT_LABEL } from "../core/pr-options.ts";

export class BuilderAgent extends CompositeAgent {
  constructor(o: AgentOpts) { super("builder", o); }
  protected stageOptions() { return { prOptions: { draft: true, labels: [KEEP_DRAFT_LABEL] } }; }
}
