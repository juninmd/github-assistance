/** Pre-flight health checks before agent execution. */
import { AGENTS_BY_NAME, resolveAgentName } from "./agents/catalog.ts";
import type { Settings } from "./config/settings.ts";

export class HealthReport {
  passed: string[] = []; warnings: string[] = []; errors: string[] = [];
  get ok() { return this.errors.length === 0; }
  summary() {
    return [...this.passed.map((p) => `  ✅ ${p}`), ...this.warnings.map((w) => `  ⚠️  ${w}`), ...this.errors.map((e) => `  ❌ ${e}`)].join("\n");
  }
}

export function runHealthChecks(s: Settings, agent: string): HealthReport {
  const r = new HealthReport();
  const all = agent === "all", target = resolveAgentName(agent), spec = target ? AGENTS_BY_NAME.get(target.agent) : undefined;
  const stageAi = !!spec?.stages.some((st) => st.requiresAi && (!target?.stage || st.name === target.stage));
  s.githubToken ? r.passed.push("GITHUB_TOKEN present") : r.errors.push("GITHUB_TOKEN is missing — GitHub operations will fail");
  if (s.enableAi && (spec?.requiresAi || stageAi || all)) {
    const p = s.aiProvider;
    if (p === "gemini" && !s.geminiApiKey) r.errors.push("AI_PROVIDER=gemini but GEMINI_API_KEY is missing");
    else if (p === "openai" && !s.openaiApiKey) r.errors.push("AI_PROVIDER=openai but OPENAI_API_KEY is missing");
    else if (p === "litellm" && !s.litellmApiKey) r.errors.push("AI_PROVIDER=litellm but LITELLM_API_KEY is missing");
    else if (p === "litellm" && !s.litellmApiBase) r.errors.push("AI_PROVIDER=litellm but LITELLM_API_BASE is missing");
    else if (p === "ollama") r.passed.push(`AI provider: ollama @ ${s.ollamaBaseUrl}`);
    if (!r.errors.length) r.passed.push(`AI provider: ${p} / model: ${s.aiModel}`);
  }
  s.telegramBotToken && s.telegramChatId ? r.passed.push("Telegram notifications enabled") : r.warnings.push("Telegram credentials missing — notifications will be silent");
  return r;
}
