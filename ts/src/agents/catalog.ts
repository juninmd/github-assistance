/** Agent catalog: single source of truth for every agent in the fleet (pure data). */
export enum AgentPriority { CRITICAL = 1, HIGH = 2, MEDIUM = 3, LOW = 4 }

export type AgentSpec = {
  name: string; className: string; emoji: string; summary: string; priority: AgentPriority;
  toggleEnv?: string; requiresAi: boolean; usesJules: boolean; notifiesTelegram: boolean;
  acceptsPrRef: boolean; dependsOn: string[]; inBatch: boolean;
};

const C = AgentPriority.CRITICAL, H = AgentPriority.HIGH, M = AgentPriority.MEDIUM, L = AgentPriority.LOW;
const spec = (
  name: string, className: string, emoji: string, summary: string, priority: AgentPriority,
  o: Partial<Omit<AgentSpec, "name" | "className" | "emoji" | "summary" | "priority">> = {},
): AgentSpec => ({
  name, className, emoji, summary, priority, requiresAi: false, usesJules: false,
  notifiesTelegram: false, acceptsPrRef: false, dependsOn: [], inBatch: true, ...o,
});

export const AGENT_CATALOG: AgentSpec[] = [
  spec("security-scanner", "SecurityScannerAgent", "🔒", "Gitleaks em todos os repositórios do owner; aplica a política no-cron-workflow", C, { toggleEnv: "SECURITY_SCANNER_ENABLED", notifiesTelegram: true }),
  spec("secret-remover", "SecretRemoverAgent", "🛡️", "Classifica achados com IA e reescreve o histórico git para remover segredos reais", C, { toggleEnv: "SECRET_REMOVER_ENABLED", requiresAi: true, notifiesTelegram: true, dependsOn: ["security-scanner"] }),
  spec("pr-assistant", "PRAssistantAgent", "🤖", "Aplica sugestões de revisão, corrige CI/conflitos e faz squash merge via MergePolicy", H, { toggleEnv: "PR_ASSISTANT_ENABLED", notifiesTelegram: true, acceptsPrRef: true }),
  spec("conflict-resolver", "ConflictResolverAgent", "⚔️", "Encontra PRs com conflito e resolve com IA de forma segura", H, { notifiesTelegram: true, acceptsPrRef: true }),
  spec("code-reviewer", "CodeReviewerAgent", "👀", "Revisa PRs: qualidade, bugs, segurança e performance", H, { toggleEnv: "CODE_REVIEWER_ENABLED", requiresAi: true, notifiesTelegram: true, acceptsPrRef: true }),
  spec("ci-health", "CIHealthAgent", "⚕️", "Monitora pipelines, detecta falhas/flaky e dispara remediação", H, { toggleEnv: "CI_HEALTH_ENABLED", notifiesTelegram: true }),
  spec("pr-sla", "PRSLAAgent", "⏱️", "Acompanha idade e tempo de revisão de PRs; alerta sobre PRs paradas", L, { toggleEnv: "PR_SLA_ENABLED" }),
  spec("senior-developer", "SeniorDeveloperAgent", "🏗️", "Segurança, CI/CD, dívida técnica, modernização e entrega do roadmap", M, { toggleEnv: "DEV_AGENT_ENABLED", requiresAi: true, usesJules: true, notifiesTelegram: true }),
  spec("dependency-manager", "DependencyManagerAgent", "📦", "CVEs primeiro, depois patch/minor seguros, em um único PR agrupado", M, { toggleEnv: "DEPENDENCY_MANAGER_ENABLED", notifiesTelegram: true }),
  spec("readme-curator", "ReadmeCuratorAgent", "📚", "Reescreve READMEs ausentes, antigos ou com nota baixa em todo o portfólio", M, { toggleEnv: "README_CURATOR_ENABLED", requiresAi: true, notifiesTelegram: true }),
  spec("intelligence-standardizer", "IntelligenceStandardizerAgent", "🧬", "Garante AGENTS.md e .agents/ consistentes nos repositórios recentes", M, { toggleEnv: "INTELLIGENCE_AGENT_ENABLED", requiresAi: true, usesJules: true, notifiesTelegram: true }),
  spec("product-manager", "ProductManagerAgent", "📋", "Mantém backlog, roadmap e documentação de produto", L, { toggleEnv: "PM_AGENT_ENABLED", requiresAi: true, usesJules: true }),
  spec("interface-developer", "InterfaceDeveloperAgent", "🎨", "UI/UX, acessibilidade e responsividade via tarefas Jules", L, { toggleEnv: "UI_AGENT_ENABLED", requiresAi: true, usesJules: true }),
  spec("project-creator", "ProjectCreatorAgent", "🚀", "Gera ideia ancorada no portfólio, cria o repositório e inicia o Jules", L, { toggleEnv: "PROJECT_CREATOR_ENABLED", requiresAi: true, usesJules: true }),
  spec("branch-cleaner", "BranchCleanerAgent", "🧹", "Remove branches mergeadas (nunca a principal nem as que têm PR aberto)", M, { toggleEnv: "BRANCH_CLEANER_ENABLED", notifiesTelegram: true }),
  spec("jules-tracker", "JulesTrackerAgent", "🔍", "Monitora sessões Jules; responde perguntas e aprova ou ajusta planos", M, { toggleEnv: "JULES_TRACKER_ENABLED", usesJules: true }),
  spec("jules-cleaner", "JulesCleanerAgent", "🗑️", "Apaga sessões Jules mais velhas que JULES_CLEANER_MAX_AGE_DAYS", M, { usesJules: true, notifiesTelegram: true, inBatch: false }),
];

export const AGENTS_BY_NAME = new Map(AGENT_CATALOG.map((s) => [s.name, s]));

export function agentNames(f: Partial<Pick<AgentSpec, "requiresAi" | "usesJules" | "notifiesTelegram" | "acceptsPrRef">> = {}): Set<string> {
  return new Set(
    AGENT_CATALOG.filter((s) => Object.entries(f).every(([k, v]) => v === undefined || (s as any)[k] === v)).map((s) => s.name),
  );
}
