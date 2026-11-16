/** Application settings: env/.env > config/features.toml > defaults. Bun loads .env natively. */
import { AGENT_CATALOG } from "../agents/catalog.ts";
import { applyFeaturesFile } from "./features.ts";
import { GitHubAppAuth } from "../webhooks/auth.ts";

const TRUE = new Set(["1", "true", "yes", "on"]);
const FALSE = new Set(["0", "false", "no", "off"]);
export const SUPPORTED_AI_PROVIDERS = ["gemini", "litellm", "ollama", "openai"] as const;
export const DEFAULT_LITELLM_API_BASE = "https://litellm.antonio-code.duckdns.org/v1";
export const DEFAULT_OLLAMA_MODEL = "qwen3:1.7b";
export const DEFAULT_MODELS: Record<string, string> = {
  gemini: "gemini-2.5-flash", litellm: "cloud/auto", ollama: DEFAULT_OLLAMA_MODEL, openai: "gpt-4o",
};

type Env = Record<string, string | undefined>;

export function parseBool(v: string | undefined, d: boolean): boolean {
  if (v == null) return d;
  const n = v.trim().toLowerCase();
  return TRUE.has(n) ? true : FALSE.has(n) ? false : d;
}
export function parsePositiveInt(v: string | undefined, d: number, name: string): number {
  if (v == null) return d;
  const n = Number(v);
  if (!Number.isInteger(n) || n <= 0 || v.trim() === "") throw new Error(`${name} must be a positive integer`);
  return n;
}
const optInt = (v: string | undefined, name: string) => (v == null ? null : parsePositiveInt(v, 1, name));

export type Settings = {
  githubToken: string; julesApiKey: string | null; githubOwner: string;
  /** agent name -> enabled (agents with a *_ENABLED toggle; default on). */
  enabled: Record<string, boolean>;
  enableAi: boolean; repositoryAllowlistPath: string; agentRunIntervalHours: number;
  geminiApiKey: string | null; openaiApiKey: string | null; litellmApiKey: string | null;
  litellmApiBase: string; aiProvider: string; aiModel: string; ollamaBaseUrl: string; openaiBaseUrl: string;
  telegramBotToken: string | null; telegramChatId: string | null;
  githubAppId: number | null; githubInstallationId: number | null; githubAppPrivateKeyPath: string | null;
  githubWebhookSecret: string | null; adminApiToken: string | null; dashboardEnabled: boolean;
  webhookDatabasePath: string; automationMode: string; webhookPurgeEnabled: boolean;
  webhookRetentionDays: number; webhookPurgeIntervalSeconds: number;
  workerEnabled: boolean; queuePollIntervalSeconds: number; queueLeaseSeconds: number;
  queueMaxAttempts: number; queueBackoffSeconds: number; maxConcurrentWorkers: number; simulationMode: boolean;
  autonomyPolicyPath: string; prioritiesPath: string;
};

function resolveAi(env: Env, enableAi: boolean): [string, string] {
  let provider = (env.AI_PROVIDER ?? "litellm").trim().toLowerCase() || "litellm";
  if (!(SUPPORTED_AI_PROVIDERS as readonly string[]).includes(provider)) {
    if (enableAi) throw new Error(`AI_PROVIDER must be one of: ${[...SUPPORTED_AI_PROVIDERS].sort().join(", ")}`);
    provider = "litellm";
  }
  const def = DEFAULT_MODELS[provider] ?? "cloud/auto";
  let model = env.AI_MODEL;
  if (model === undefined && provider === "ollama") model = env.OLLAMA_MODEL;
  return [provider, (model || def).trim() || def];
}

export async function settingsFromEnv(env: Env = process.env): Promise<Settings> {
  applyFeaturesFile(undefined, env);
  let token = env.GITHUB_TOKEN || env.GH_PAT;
  const appId = optInt(env.GITHUB_APP_ID, "GITHUB_APP_ID");
  const instId = optInt(env.GITHUB_INSTALLATION_ID, "GITHUB_INSTALLATION_ID");
  const keyPath = env.GITHUB_APP_PRIVATE_KEY_PATH ?? null;
  if (!token && appId && instId && keyPath) {
    try { token = await new GitHubAppAuth(appId, instId, keyPath).installationToken(); }
    catch (e: any) { throw new Error(`Failed to obtain GitHub App installation token: ${e?.message ?? e}`); }
  }
  if (!token) throw new Error("GITHUB_TOKEN environment variable is required");
  const enableAi = parseBool(env.ENABLE_AI, false);
  const [aiProvider, aiModel] = resolveAi(env, enableAi);
  const enabled: Record<string, boolean> = {};
  for (const s of AGENT_CATALOG) if (s.toggleEnv) enabled[s.name] = parseBool(env[s.toggleEnv], true);
  const pi = (n: string, d: number) => parsePositiveInt(env[n], d, n);
  return {
    githubToken: token, julesApiKey: env.JULES_API_KEY ?? null, githubOwner: env.GITHUB_OWNER ?? "juninmd",
    enabled, enableAi, repositoryAllowlistPath: env.REPOSITORY_ALLOWLIST_PATH ?? "config/repositories.json",
    agentRunIntervalHours: pi("AGENT_RUN_INTERVAL_HOURS", 24),
    geminiApiKey: env.GEMINI_API_KEY ?? null, openaiApiKey: env.OPENAI_API_KEY ?? null, litellmApiKey: env.LITELLM_API_KEY ?? null,
    litellmApiBase: env.LITELLM_API_BASE ?? DEFAULT_LITELLM_API_BASE, aiProvider, aiModel,
    ollamaBaseUrl: env.OLLAMA_BASE_URL ?? "http://localhost:11434", openaiBaseUrl: env.OPENAI_BASE_URL ?? "https://api.openai.com/v1",
    telegramBotToken: env.TELEGRAM_BOT_TOKEN || env.telegram_bot_token || null,
    telegramChatId: env.TELEGRAM_CHAT_ID || env.telegram_chat_id || null,
    githubAppId: appId, githubInstallationId: instId, githubAppPrivateKeyPath: keyPath,
    githubWebhookSecret: env.GITHUB_WEBHOOK_SECRET ?? null, adminApiToken: env.ADMIN_API_TOKEN || null,
    dashboardEnabled: parseBool(env.DASHBOARD_ENABLED, true),
    webhookDatabasePath: env.WEBHOOK_DATABASE_PATH ?? "data/webhooks.db",
    automationMode: (env.AUTOMATION_MODE ?? "observe").trim().toLowerCase(),
    webhookPurgeEnabled: parseBool(env.WEBHOOK_PURGE_ENABLED, true),
    webhookRetentionDays: pi("WEBHOOK_RETENTION_DAYS", 3), webhookPurgeIntervalSeconds: pi("WEBHOOK_PURGE_INTERVAL_SECONDS", 21600),
    workerEnabled: parseBool(env.WORKER_ENABLED, true), queuePollIntervalSeconds: pi("QUEUE_POLL_INTERVAL_SECONDS", 15),
    queueLeaseSeconds: pi("QUEUE_LEASE_SECONDS", 300), queueMaxAttempts: pi("QUEUE_MAX_ATTEMPTS", 3),
    queueBackoffSeconds: pi("QUEUE_BACKOFF_SECONDS", 60), maxConcurrentWorkers: pi("MAX_CONCURRENT_WORKERS", 1),
    simulationMode: parseBool(env.SIMULATION_MODE, false),
    autonomyPolicyPath: env.AUTONOMY_POLICY_PATH ?? "config/autonomy.json", prioritiesPath: env.PRIORITIES_PATH ?? "config/priorities.json",
  };
}
