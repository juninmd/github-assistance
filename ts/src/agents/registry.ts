/** Agent registry: lazy-loads `agents/<package>/agent.ts`; unported agents fail loudly. */
import { existsSync } from "node:fs";
import { join } from "node:path";
import { RepositoryAllowlist } from "../config/allowlist.ts";
import { DEFAULT_MODELS, type Settings } from "../config/settings.ts";
import { GithubClient } from "../github/client.ts";
import { TelegramNotifier } from "../notifications/telegram.ts";
import { agentNames, AGENTS_BY_NAME } from "./catalog.ts";
import { agentDir } from "./core/utils.ts";
import type { BaseAgent } from "./base-agent.ts";

export const AGENTS_WITH_AI = agentNames({ requiresAi: true });
export const AGENTS_WITH_TELEGRAM = agentNames({ notifiesTelegram: true });
export const AGENTS_WITH_PR_REF = agentNames({ acceptsPrRef: true });

export type AI = { provider: string; model: string; config: { apiKey?: string | null; baseUrl?: string | null } };
export const registeredNames = () => [...AGENTS_BY_NAME.keys()];

export function createBaseDeps(s: Settings) {
  return {
    githubClient: new GithubClient(s.githubToken),
    allowlist: new RepositoryAllowlist(s.repositoryAllowlistPath),
    telegram: new TelegramNotifier(s.telegramBotToken, s.telegramChatId),
  };
}

export function buildAiConfig(s: Settings, provider?: string, model?: string): AI {
  const p = provider || s.aiProvider;
  const m = model || (provider ? DEFAULT_MODELS[p] ?? s.aiModel : s.aiModel);
  const config: AI["config"] = {};
  if (p === "gemini") config.apiKey = s.geminiApiKey;
  else if (p === "openai") { config.apiKey = s.openaiApiKey; config.baseUrl = s.openaiBaseUrl; }
  else if (p === "ollama") config.baseUrl = s.ollamaBaseUrl;
  else if (p === "litellm") { config.apiKey = s.litellmApiKey; config.baseUrl = s.litellmApiBase; }
  return { provider: p, model: m, config };
}

export const isPorted = (name: string) => existsSync(join(agentDir(name), "agent.ts"));

export type AgentCtor = new (o: Record<string, any>) => BaseAgent;
export async function createAgent(name: string, s: Settings, o: { provider?: string; model?: string; prRef?: string } = {}): Promise<BaseAgent> {
  const spec = AGENTS_BY_NAME.get(name);
  if (!spec) throw new Error(`unknown agent: ${name}`);
  if (!isPorted(name)) throw new Error(`agent '${name}' ainda não foi portado para Bun`);
  const mod = await import(join(agentDir(name), "agent.ts"));
  const Cls: AgentCtor = mod[spec.className];
  if (!Cls) throw new Error(`${spec.className} not exported by agents/${name}/agent.ts`);
  const kwargs: Record<string, any> = { ...createBaseDeps(s), targetOwner: s.githubOwner };
  kwargs.telegram = new TelegramNotifier(s.telegramBotToken, s.telegramChatId, `[${name.replace(/-/g, " ").toUpperCase()}]`);
  if (AGENTS_WITH_AI.has(name)) {
    if (!s.enableAi) throw new Error(`Agent '${name}' requires AI but ENABLE_AI is false.`);
    kwargs.ai = buildAiConfig(s, o.provider, o.model);
  }
  if (name === "pr-assistant") Object.assign(kwargs, { commentAiEnabled: s.enableAi, simulationMode: s.simulationMode, autonomyPolicyPath: s.autonomyPolicyPath, settings: s });
  if (AGENTS_WITH_PR_REF.has(name) && o.prRef) kwargs.prRef = o.prRef;
  return new Cls(kwargs);
}
