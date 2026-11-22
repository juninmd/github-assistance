/** Flow Watch - observe-only: failing pipelines and stale PRs go to Telegram; fixing is the PR Assistant's job. */
import type { AgentOpts } from "../agent-types.ts";
import type { StageSpec } from "../catalog.ts";
import { CompositeAgent } from "../core/composite.ts";

export class FlowWatchAgent extends CompositeAgent {
  constructor(o: AgentOpts) { super("flow-watch", o); }
  protected stageOptions(stage: StageSpec) { return stage.name === "ci" ? { remediate: false } : { nudge: false }; }
}
