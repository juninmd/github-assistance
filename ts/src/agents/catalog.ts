/** Agent catalog: single source of truth for every agent in the fleet (pure data). */
export enum AgentPriority { CRITICAL = 1, HIGH = 2, MEDIUM = 3, LOW = 4 }

/** A step of a composite agent: one of the former agents, kept as an internal, independently testable unit. */
export type StageSpec = { name: string; dir: string; className: string; toggleEnv?: string; requiresAi?: boolean };

export type AgentSpec = {
  name: string; className: string; emoji: string; summary: string; priority: AgentPriority;
  toggleEnv?: string; requiresAi: boolean; notifiesTelegram: boolean;
  acceptsPrRef: boolean; dependsOn: string[]; inBatch: boolean; stages: StageSpec[];
};

const C = AgentPriority.CRITICAL, H = AgentPriority.HIGH, M = AgentPriority.MEDIUM, L = AgentPriority.LOW;
const spec = (
  name: string, className: string, emoji: string, summary: string, priority: AgentPriority,
  o: Partial<Omit<AgentSpec, "name" | "className" | "emoji" | "summary" | "priority">> = {},
): AgentSpec => ({
  name, className, emoji, summary, priority, requiresAi: false,
  notifiesTelegram: false, acceptsPrRef: false, dependsOn: [], inBatch: true, stages: [], ...o,
});
const stage = (name: string, dir: string, className: string, o: Partial<StageSpec> = {}): StageSpec => ({ name, dir, className, ...o });

export const AGENT_CATALOG: AgentSpec[] = [
  spec("secret-guard", "SecretGuardAgent", "🔒", "Gitleaks no portfólio e política no-cron; remove segredo do histórico só com aprovação do dono (Telegram ou /aprovar)", C, {
    toggleEnv: "SECRET_GUARD_ENABLED", notifiesTelegram: true,
    stages: [stage("scan", "security_scanner", "SecurityScannerAgent", { toggleEnv: "SECURITY_SCANNER_ENABLED" }),
      stage("remove", "secret_remover", "SecretRemoverAgent", { toggleEnv: "SECRET_REMOVER_ENABLED", requiresAi: true })],
  }),
  spec("pr-assistant", "PRAssistantAgent", "🤖", "Dono de todo PR: gate AGENTS.md, revisão do diff, SAST, conflitos, checks e squash merge via MergePolicy", H, { toggleEnv: "PR_ASSISTANT_ENABLED", notifiesTelegram: true, acceptsPrRef: true }),
  spec("flow-watch", "FlowWatchAgent", "⚕️", "Observa pipelines com falha e PRs paradas; só reporta no Telegram", H, {
    toggleEnv: "FLOW_WATCH_ENABLED", notifiesTelegram: true,
    stages: [stage("ci", "ci_health", "CIHealthAgent", { toggleEnv: "CI_HEALTH_ENABLED" }), stage("sla", "pr_sla", "PRSLAAgent", { toggleEnv: "PR_SLA_ENABLED" })],
  }),
  spec("dependency-manager", "DependencyManagerAgent", "📦", "CVEs primeiro, depois patch/minor seguros, em um único PR agrupado", M, { toggleEnv: "DEPENDENCY_MANAGER_ENABLED", notifiesTelegram: true }),
  spec("repo-standards", "RepoStandardsAgent", "🧬", "AGENTS.md, .agents/ e README em todos os repositórios ativos", M, {
    toggleEnv: "REPO_STANDARDS_ENABLED", requiresAi: true, notifiesTelegram: true,
    stages: [stage("agents-md", "intelligence_standardizer", "IntelligenceStandardizerAgent", { toggleEnv: "INTELLIGENCE_AGENT_ENABLED" }),
      stage("readme", "readme_curator", "ReadmeCuratorAgent", { toggleEnv: "README_CURATOR_ENABLED" })],
  }),
  spec("branch-cleaner", "BranchCleanerAgent", "🧹", "Remove branches mergeadas (nunca a principal nem as que têm PR aberto)", M, { toggleEnv: "BRANCH_CLEANER_ENABLED", notifiesTelegram: true }),
  spec("builder", "BuilderAgent", "🏗️", "Planeja e implementa melhorias em PRs draft; nunca faz merge", L, {
    toggleEnv: "BUILDER_ENABLED", requiresAi: true, notifiesTelegram: true,
    stages: [stage("plan", "product_manager", "ProductManagerAgent", { toggleEnv: "PM_AGENT_ENABLED" }),
      stage("code", "senior_developer", "SeniorDeveloperAgent", { toggleEnv: "DEV_AGENT_ENABLED" }),
      stage("ui", "interface_developer", "InterfaceDeveloperAgent", { toggleEnv: "UI_AGENT_ENABLED" })],
  }),
  spec("project-creator", "ProjectCreatorAgent", "🚀", "Gera ideia ancorada no portfólio, cria o repositório e inicia a implementação com opencode", L, { toggleEnv: "PROJECT_CREATOR_ENABLED", requiresAi: true }),
];

export const AGENTS_BY_NAME = new Map(AGENT_CATALOG.map((s) => [s.name, s]));

/** Former agent names: still accepted by the CLI so existing CronJobs keep running the same unit of work. */
export const AGENT_ALIASES: Record<string, { agent: string; stage?: string; retired?: boolean }> = {
  "security-scanner": { agent: "secret-guard", stage: "scan" },
  "secret-remover": { agent: "secret-guard", stage: "remove" },
  // Retired: their work now runs inside pr-assistant's own schedule; a leftover CronJob becomes a no-op, not a second PR pass.
  "code-reviewer": { agent: "pr-assistant", retired: true },
  "conflict-resolver": { agent: "pr-assistant", retired: true },
  "ci-health": { agent: "flow-watch", stage: "ci" },
  "pr-sla": { agent: "flow-watch", stage: "sla" },
  "intelligence-standardizer": { agent: "repo-standards", stage: "agents-md" },
  "readme-curator": { agent: "repo-standards", stage: "readme" },
  "product-manager": { agent: "builder", stage: "plan" },
  "senior-developer": { agent: "builder", stage: "code" },
  "interface-developer": { agent: "builder", stage: "ui" },
};

/** Resolve a CLI name (current or former) to the agent that runs it, plus the single stage a former name maps to. */
export function resolveAgentName(name: string): { agent: string; stage?: string; retired?: boolean } | null {
  if (AGENTS_BY_NAME.has(name)) return { agent: name };
  return AGENT_ALIASES[name] ?? null;
}

export function agentNames(f: Partial<Pick<AgentSpec, "requiresAi" | "notifiesTelegram" | "acceptsPrRef">> = {}): Set<string> {
  return new Set(
    AGENT_CATALOG.filter((s) => Object.entries(f).every(([k, v]) => v === undefined || (s as any)[k] === v)).map((s) => s.name),
  );
}
