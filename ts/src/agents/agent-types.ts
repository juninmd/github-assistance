import type { BaseDeps } from "./base-agent.ts";
/** Constructor options every agent receives from the registry. */
export type AgentOpts = BaseDeps & Record<string, any>;
import { getAiClient, type AIClient } from "../ai/client.ts";
import { DEFAULT_OLLAMA_MODEL } from "../config/settings.ts";
/** Builds the AI client described by `AgentOpts.ai` (defaults to Ollama). */
export function makeAi(ai?: { provider?: string; model?: string; config?: { apiKey?: string | null; baseUrl?: string | null } }): { client: AIClient; label: string } {
  const provider = ai?.provider ?? "ollama", model = ai?.model ?? DEFAULT_OLLAMA_MODEL;
  return { client: getAiClient(provider, { model, ...(ai?.config ?? {}) }), label: `${provider}/${model}` };
}
