/**
 * Advisory PR code review: free opencode first, cluster cloud/auto fallback. Clones the PR head, obtains a JSON verdict, and on
 * blocking findings asks the model for a patch, has it independently reviewed, then pushes. Every failure degrades to a
 * diff-only LiteLLM call or no review; it never throws into the run and never touches the merge path.
 */
import { rmSync, mkdtempSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import type { GithubClient, PR } from "../../github/client.ts";
import { getLogger } from "../../utils/logger.ts";
import { run } from "../../utils/proc.ts";
import { semanticMessage } from "../core/commit-message.ts";
import { buildOriginMetadata } from "../core/utils.ts";
import * as credentialGate from "./credential-gate.ts";
import * as evidence from "./pr-evidence.ts";
import { collectDiff } from "./pr-diff.ts";
import { rulesBlock } from "./review-advisories.ts";
import { shouldAutofix } from "./review-authors.ts";
import * as flags from "./review-flags.ts";
import * as git from "./review-git.ts";
import { validateFindings, visibleFromPr } from "./review-lines.ts";
import { candidateModels } from "./review-models.ts";
import * as pkg from "./review-packages.ts";
import * as patch from "./review-patch.ts";
import * as rv from "./review-verdict.ts";
import * as ws from "./review-workspace.ts";

const log = getLogger("review");
const MAX_DIFF_CHARS = 12000, FALLBACK_ATTEMPTS = 2;
type Ai = { generate(p: string): Promise<string> } | null | undefined;

export const autofixEnabled = () => flags.enabled("REVIEW_AUTOFIX_ENABLED", true) && !flags.reviewDryRun();

export function instructions(pr: PR): string {
  return "Você é um engenheiro sênior revisando um pull request. Use o agente `code-review` " +
    "(opencode 2) e a skill `code-review` (mais `security-ops`/`test-engineering` quando " +
    "fizer sentido) e leia o repositório no diretório atual. Cubra quatro frentes: " +
    "(1) qualidade/correção do código; (2) segurança; (3) regra de negócio: a mudança " +
    "cumpre o que título e descrição prometem, sem quebrar invariantes ou fluxos " +
    "existentes; (4) conflitos: marcadores `<<<<<<<`/`>>>>>>>` esquecidos ou resolução " +
    "que descartou lógica de um dos lados. Aponte apenas defeitos reais; ignore estilo.\n\n" +
    "Responda com APENAS um objeto JSON, em português, sem texto fora do JSON:\n" +
    '{"verdict":"APPROVE|REQUEST_CHANGES","summary":"resumo curto",' +
    '"findings":[{"file":"caminho","line":0,"severity":"error|warn|nit","issue":"..."}]}\n' +
    "Verifique também se o diff expõe credenciais (tokens, chaves privadas, senhas ou " +
    "URLs com usuário:senha em texto plano). Qualquer credencial exposta é severity " +
    "error e deve usar REQUEST_CHANGES.\n" +
    "Use APPROVE quando não houver problema bloqueante.\n" +
    `${rulesBlock()}\n\n` + `Título do PR: ${pr.title}\n`;
}
export async function jsonPrompt(gh: GithubClient, pr: PR, diff: string, rules = ""): Promise<string> {
  return `${instructions(pr)}\n${rules}\nDiff:\n${diff || (await collectDiff(gh, pr))}`;
}
export function fixInstructions(v: rv.ReviewVerdict): string {
  const findings = v.findings.map((f) => `- \`${f.file}\` (linha ${f.line || "?"}, ${f.severity}): ${f.issue}`).join("\n");
  return "Você é um engenheiro sênior. Corrija APENAS os problemas listados abaixo no repositório deste PR.\n" +
    "Use a ferramenta de edição para alterar os arquivos de verdade — não descreva a correção nem responda em texto.\n" +
    "Regras: mudanças mínimas e seguras; não refatore código não relacionado; não altere " +
    "testes para mascarar falhas, corrija a causa.\n\n" + `Problemas:\n${findings}\n`;
}
/** Diff-only LiteLLM verdict; retries once because models occasionally emit malformed JSON. */
export async function fallbackVerdict(gh: GithubClient, pr: PR, ai: Ai): Promise<rv.ReviewVerdict | null> {
  if (!ai) return null;
  for (let attempt = 0; attempt < FALLBACK_ATTEMPTS; attempt++) {
    let text: string;
    try { text = await ai.generate(await jsonPrompt(gh, pr, "")); } catch { return null; }
    const v = rv.parseReview(text, "cloud/auto (litellm)");
    if (v) return { ...v, harness: "litellm (só diff)", skills_checked: true };
    log.warning(`LLM review returned unusable JSON for PR #${pr.number} (attempt ${attempt + 1}/${FALLBACK_ATTEMPTS})`);
  }
  return null;
}
const withTrace = (v: rv.ReviewVerdict): rv.ReviewVerdict => {
  const t = ws.lastTrace();
  return t ? { ...v, harness: t.harness, skills_used: t.skills_used, skills_checked: t.structured } : v;
};
async function reviewPackage(gh: GithubClient, dir: string, pr: PR, candidates: string[], diff: string, rules: string) {
  const prompt = await jsonPrompt(gh, pr, diff, rules);
  for (const model of candidates) {
    ws.resetTrace();
    const out = await ws.runOpencode(dir, prompt, model, ws.reviewTimeout());
    const v = out ? rv.parseReview(out, model) : null;
    if (v) return withTrace(v);
  }
  return null;
}
/** Review in packages of related files so big PRs are not cut at 12k chars. */
export async function reviewWithModels(gh: GithubClient, dir: string, pr: PR, candidates: string[]): Promise<rv.ReviewVerdict | null> {
  const full = await ws.localDiff(dir, pr.base.ref, 1e7);
  const sections = pkg.splitByFile(full);
  const packages = Object.keys(sections).length ? pkg.buildPackages(sections, MAX_DIFF_CHARS) : [{ "": full }];
  const limit = pkg.maxPackages();
  const skipped = packages.slice(limit).reduce((n, p) => n + Object.keys(p).length, 0);
  const rules = pkg.loadRules(dir);
  const verdicts: rv.ReviewVerdict[] = [];
  for (const files of packages.slice(0, limit)) {
    const v = await reviewPackage(gh, dir, pr, candidates, Object.values(files).join("\n"), pkg.rulesText(rules, Object.keys(files)));
    if (!v) { if (!verdicts.length) return null; continue; }
    verdicts.push(v);
    candidates = [...new Set([v.model, ...candidates].filter(Boolean))];
  }
  if (!verdicts.length) return null;
  let merged = verdicts.length > 1 ? pkg.mergeVerdicts(verdicts) : verdicts[0]!;
  if (skipped) merged = { ...merged, summary: `${merged.summary} (${skipped} arquivo(s) fora do limite de ${limit} pacotes não foram revisados.)`.trim() };
  return merged;
}
const FIX_REVIEW_RULES = "ATENÇÃO: o diff abaixo é uma CORREÇÃO AUTOMÁTICA ainda não enviada. Seja rigoroso: use " +
  "REQUEST_CHANGES se ela introduzir bug, regressão ou falha de segurança, alterar/desabilitar " +
  "testes para mascarar falhas, deixar código incompleto, ou fizer mais do que o necessário.\n\n";
export type FixStatus = "approved" | "rejected" | "unavailable";
/** Review an unpushed fix. */
export async function reviewFix(gh: GithubClient, dir: string, pr: PR, candidates: string[], diff?: string): Promise<[FixStatus, rv.ReviewVerdict | null]> {
  if (diff === undefined) diff = await ws.localDiff(dir, pr.base.ref, MAX_DIFF_CHARS, true);
  if (!diff.trim()) return ["rejected", null];
  const prompt = FIX_REVIEW_RULES + (await jsonPrompt(gh, pr, diff.slice(0, MAX_DIFF_CHARS)));
  for (const model of candidates) {
    ws.resetTrace();
    const out = await ws.runOpencode(dir, prompt, model, ws.reviewTimeout());
    const parsed = out ? rv.parseReview(out, model) : null;
    if (!parsed) continue;
    const fresh = withTrace(parsed);
    const blocking = rv.blocks(fresh, flags.gateMinSeverity());
    const onlyMinor = fresh.findings.length > 0 && !blocking;
    return [(rv.isApproved(fresh) || onlyMinor) && !blocking ? "approved" : "rejected", fresh];
  }
  return ["unavailable", null];
}
async function pushIfVerified(gh: GithubClient, dir: string, pr: PR, v: rv.ReviewVerdict, candidates: string[], message: string): Promise<rv.ReviewVerdict | null> {
  const [status, checked] = await reviewFix(gh, dir, pr, candidates);
  if (status !== "approved" || !checked) {
    log.warning(`auto-fix for PR #${pr.number} rejected by verification; not pushed`);
    await git.discardChanges(dir);
    return null;
  }
  const [ok, sha] = await git.commitAndPush(dir, pr.head.ref, message);
  if (!ok) return null;
  return { ...v, verdict: rv.APPROVE, summary: checked.summary || v.summary, findings: checked.findings, model: checked.model || v.model,
    skills_used: [...new Set([...v.skills_used, ...checked.skills_used])], skills_checked: v.skills_checked || checked.skills_checked, fixed: true, commit: sha };
}
export async function applyFixes(gh: GithubClient, dir: string, pr: PR, v: rv.ReviewVerdict, candidates: string[]): Promise<rv.ReviewVerdict> {
  const message = semanticMessage("fix", "review", "aplica correções da revisão automática", buildOriginMetadata("pr_assistant", v.model || "opencode"));
  const last = candidates[candidates.length - 1]!;
  for (const model of new Set([v.model || last, last])) {
    const p = await patch.requestPatch(dir, v, model);
    if (p && (await patch.applyPatch(dir, p))) { const pushed = await pushIfVerified(gh, dir, pr, v, candidates, message); if (pushed) return pushed; }
  }
  await ws.runOpencode(dir, fixInstructions(v), last, ws.reviewTimeout());
  return (await pushIfVerified(gh, dir, pr, v, candidates, message)) ?? v;
}
async function viaClone(gh: GithubClient, pr: PR, token: string): Promise<rv.ReviewVerdict | null> {
  const candidates = await candidateModels();
  const autofix = autofixEnabled() && shouldAutofix(pr.user?.login ?? "");
  let tmp = "";
  try {
    tmp = mkdtempSync(join(tmpdir(), ws.REVIEW_PREFIX));
    const dir = await ws.clonePrHead(pr, tmp, token);
    ws.writeOpencodeConfig(join(homedir(), ".config", "opencode"));
    let v = await reviewWithModels(gh, dir, pr, candidates);
    if (v && !rv.isApproved(v) && v.findings.length && autofix) v = await applyFixes(gh, dir, pr, v, candidates);
    return v;
  } catch { return null; } finally { if (tmp) rmSync(tmp, { recursive: true, force: true }); }
}
async function validated(gh: GithubClient, pr: PR, v: rv.ReviewVerdict | null) {
  if (!v || !v.findings.length) return v;
  try { return { ...v, findings: validateFindings(v.findings, await visibleFromPr(gh, pr)) }; } catch { return v; }
}
function withEvidence(pr: PR, v: rv.ReviewVerdict | null) {
  if (!v) return null;
  const f = evidence.evidenceFinding(pr.body);
  return f ? { ...v, findings: [...v.findings, f] } : v;
}
/** Review verdict, or null when the review could not run. */
export async function runReview(gh: GithubClient, pr: PR, ai?: Ai): Promise<rv.ReviewVerdict | null> {
  ws.cleanupStaleReviewDirs();
  let leak: rv.ReviewVerdict | null;
  try { leak = credentialGate.credentialVerdict(await credentialGate.prAddedText(gh, pr)); }
  catch (e) {
    log.warning(`credential scan failed for PR #${pr.number}: ${(e as Error).name}`);
    return rv.mkVerdict({ verdict: rv.REQUEST_CHANGES, summary: "PR bloqueado: varredura de credenciais não pôde ser executada.",
      findings: [rv.mkFinding({ file: "(diff)", severity: "error", issue: "Varredura de credenciais falhou." })], model: credentialGate.MODEL_LABEL });
  }
  if (leak) { log.warning(`PR #${pr.number} blocked: possible credential in added lines`); return leak; }
  const token = process.env.GITHUB_TOKEN || process.env.GH_PAT || "";
  const v = token ? await viaClone(gh, pr, token) : null;
  return withEvidence(pr, await validated(gh, pr, v ?? (await fallbackVerdict(gh, pr, ai))));
}
const findingsText = (v: rv.ReviewVerdict | null) => !v ? "fix review did not approve the change"
  : "fix review rejected the change:\n" + (v.findings.map((f) => `- ${f.file}:${f.line || "?"} (${f.severity}) ${f.issue}`).join("\n") || `- ${v.summary}`);
/** Independent review of the uncommitted changes in `dir` (incl. new files). */
export async function verifyPendingFix(gh: GithubClient, dir: string, pr: PR): Promise<[boolean, string]> {
  const candidates = await candidateModels();
  let status: FixStatus, checked: rv.ReviewVerdict | null = null;
  try {
    ws.writeOpencodeConfig(join(homedir(), ".config", "opencode"));
    await run(["git", "add", "-N", "."], { cwd: dir, timeoutMs: 60_000 });
    const proc = await run(["git", "diff", "HEAD", "--unified=3"], { cwd: dir, timeoutMs: 60_000 });
    [status, checked] = await reviewFix(gh, dir, pr, candidates, proc.stdout || "");
  } catch (e) { status = "unavailable"; log.warning(`fix review error for PR #${pr.number}: ${(e as Error).name}`); }
  if (status === "approved") return [true, `fix review approved (${checked?.model || "opencode"})`];
  if (status === "unavailable") return flags.enabled("PIPELINE_FIX_REQUIRE_REVIEW", false)
    ? [false, "fix review unavailable (PIPELINE_FIX_REQUIRE_REVIEW is on)"] : [true, "fix review unavailable; deterministic checks only"];
  return [false, findingsText(checked)];
}
