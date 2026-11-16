import type { BaseDeps } from "./base-agent.ts";
/** Constructor options every agent receives from the registry. */
export type AgentOpts = BaseDeps & Record<string, any>;
