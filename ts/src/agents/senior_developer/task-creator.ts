/** Creates opencode tasks from analysis results. */
import type { BaseAgent } from "../base-agent.ts";

type R = Record<string, any>;
export type AnalyzerKey = "analyzeSecurity" | "analyzeCicd" | "aiPoweredAudit" | "analyzeRoadmapFeatures" | "analyzeTechDebt" | "analyzeModernization" | "analyzePerformance";
export type CreatorKey = "createSecurityTask" | "createCicdTask" | "createAuditRemediationTask" | "createFeatureImplementationTask" | "createTechDebtTask" | "createModernizationTask" | "createPerformanceTask";

export const ANALYSIS_METHODS: [AnalyzerKey, CreatorKey, string, string][] = [
  ["analyzeSecurity", "createSecurityTask", "security_tasks", "needs_attention"],
  ["analyzeCicd", "createCicdTask", "cicd_tasks", "needs_improvement"],
  ["aiPoweredAudit", "createAuditRemediationTask", "security_tasks", "needs_attention"],
  ["analyzeRoadmapFeatures", "createFeatureImplementationTask", "feature_tasks", "has_features"],
  ["analyzeTechDebt", "createTechDebtTask", "tech_debt_tasks", "needs_attention"],
  ["analyzeModernization", "createModernizationTask", "modernization_tasks", "needs_modernization"],
  ["analyzePerformance", "createPerformanceTask", "performance_tasks", "needs_optimization"],
];
const bullets = (xs: string[]) => xs.map((x) => `- ${x}`).join("\n");

export class SeniorDeveloperTaskCreator {
  constructor(private agent: BaseAgent) {}
  private make(repo: string, template: string, vars: R, title: string) {
    return this.agent.createOpencodeTask(repo, this.agent.loadTaskInstructions(template, { repository: repo, ...vars }), title);
  }
  createTechDebtTask(r: string, a: R) { return this.make(r, "task-instructions-tech-debt.md", { details: a.details ?? "General code quality improvements." }, `Tech Debt Cleanup for ${r}`); }
  createModernizationTask(r: string, a: R) { return this.make(r, "task-instructions-modernization.md", { details: a.details ?? "Migrate legacy patterns to modern standards." }, `Modernization for ${r}`); }
  createPerformanceTask(r: string, a: R) { return this.make(r, "task-instructions-performance.md", { details: a.details ?? "Identify and fix performance bottlenecks." }, `Performance Tuning for ${r}`); }
  createSecurityTask(r: string, a: R) { return this.make(r, "task-instructions-security.md", { issues: bullets(a.issues ?? []) }, `Security Hardening for ${r}`); }
  createCicdTask(r: string, a: R) { return this.make(r, "task-instructions-cicd.md", { improvements: bullets(a.improvements ?? []) }, `CI/CD Pipeline for ${r}`); }
  createFeatureImplementationTask(r: string, a: R) { return this.make(r, "task-instructions-features.md", { features: (a.features ?? []).map((f: R) => `- ${f.title} (#${f.number})`).join("\n") }, `Feature Implementation for ${r}`); }
  createAuditRemediationTask(r: string, a: R) { return this.make(r, "task-instructions-audit.md", { findings: bullets(a.findings ?? []), criticality: a.criticality ?? "medium" }, `Audit Remediation for ${r} (${a.criticality ?? "medium"})`); }
  createFeatureEnhancementTask(r: string, a: R) { return this.make(r, "task-instructions-feature-enhancement.md", { suggestion: a.suggestion ?? "New Feature", details: a.details ?? "Impactful feature improvement." }, `Feature Enhancement: ${a.suggestion ?? "New Feature"}`); }
}
