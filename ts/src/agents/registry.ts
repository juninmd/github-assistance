/** Agent registry: lazy-loads `agents/<package>/agent.ts`; unported agents fail loudly. */
import { existsSync } from "node:fs";
import { join } from "node:path";
import { RepositoryAllowlist } from "../config/allowlist.ts";
import { DEFAULT_MODELS, type Settings } from "../config/settings.ts";
import { GithubClient } from "../github/client.ts";
import { TelegramNotifier } from "../notifications/telegram.ts";
import { agentNames, AGENTS_BY_NAME, resolveAgentName } from "./catalog.ts";
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
    allowlist: new RepositoryAllowlist(s.repositoryAllowlistPath, process.env.REPOSITORY_ALLOWLIST_ENFORCE === "true"),
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
  const target = resolveAgentName(name);
  const spec = target ? AGENTS_BY_NAME.get(target.agent) : undefined;
  if (!target || !spec) throw new Error(`unknown agent: ${name}`);
  if (target.retired) {
    const reason = `'${name}' is retired: its work runs inside ${target.agent}; remove this schedule`;
    return { name, run: async () => { console.warn(`[WARNING] ${reason}`); return { status: "skipped", reason }; } } as unknown as BaseAgent;
  }
  const agent = target.agent, stage = spec.stages.find((st) => st.name === target.stage);
  if (!isPorted(agent)) throw new Error(`agent '${agent}' ainda não foi portado para Bun`);
  const mod = await import(join(agentDir(agent), "agent.ts"));
  const Cls: AgentCtor = mod[spec.className];
  if (!Cls) throw new Error(`${spec.className} not exported by agents/${agent}/agent.ts`);
  const kwargs: Record<string, any> = { ...createBaseDeps(s), targetOwner: s.githubOwner };
  kwargs.telegram = new TelegramNotifier(s.telegramBotToken, s.telegramChatId, `[${name.replace(/-/g, " ").toUpperCase()}]`);
  const needsAi = AGENTS_WITH_AI.has(agent) || !!stage?.requiresAi;
  if (needsAi && !s.enableAi) throw new Error(`Agent '${name}' requires AI but ENABLE_AI is false.`);
  // A composite with an optional AI stage (secret-guard) gets the client only when AI is on; the stage is skipped otherwise.
  if (needsAi || (s.enableAi && spec.stages.some((st) => st.requiresAi))) kwargs.ai = buildAiConfig(s, o.provider, o.model);
  if (stage) kwargs.stage = stage.name;
  if (agent === "pr-assistant") Object.assign(kwargs, { commentAiEnabled: s.enableAi, simulationMode: s.simulationMode, autonomyPolicyPath: s.autonomyPolicyPath, settings: s });
  if (AGENTS_WITH_PR_REF.has(agent) && o.prRef) kwargs.prRef = o.prRef;
  return new Cls(kwargs);
}
