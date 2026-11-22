/** Fleet view: the agent catalog joined with the live Settings toggles. */
import { AGENT_CATALOG, AgentPriority, type AgentSpec } from "./catalog.ts";
import type { Settings } from "../config/settings.ts";

export function blockedReason(s: AgentSpec, st: Settings): string | null {
  if (s.toggleEnv && st.enabled[s.name] === false) return `${s.toggleEnv}=false`;
  if (s.requiresAi && !st.enableAi) return "ENABLE_AI=false";
  return null;
}

export function fleetStatus(st: Settings) {
  return {
    agents: AGENT_CATALOG.map((s) => {
      const reason = blockedReason(s, st);
      return {
        name: s.name, emoji: s.emoji, summary: s.summary, priority: AgentPriority[s.priority].toLowerCase(),
        requires_ai: s.requiresAi, notifies_telegram: s.notifiesTelegram,
        accepts_pr_ref: s.acceptsPrRef, depends_on: s.dependsOn, in_batch: s.inBatch,
        toggle_env: s.toggleEnv ?? null, runnable: reason === null, blocked_reason: reason,
      };
    }),
    ai: { enabled: st.enableAi, provider: st.aiProvider, model: st.aiModel },
    owner: st.githubOwner,
  };
}
