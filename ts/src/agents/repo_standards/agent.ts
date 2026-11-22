/** Repo Standards - AGENTS.md, .agents/ and README kept short, specific and present in every active repository. */
import type { AgentOpts } from "../agent-types.ts";
import { CompositeAgent } from "../core/composite.ts";

export class RepoStandardsAgent extends CompositeAgent {
  constructor(o: AgentOpts) { super("repo-standards", o); }
}
