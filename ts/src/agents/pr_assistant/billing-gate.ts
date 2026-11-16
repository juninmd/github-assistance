/**
 * Merge handling for repos whose GitHub Actions cannot start (billing/spending limit). CI says nothing about the code, so the
 * bot still merges but only after its own credential scan of the added lines finds nothing, leaving a disclaimer on the PR.
 */
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve, sep } from "node:path";
import { scanClone, scanText } from "../../utils/secret-scan.ts";
import type { GithubClient, PR } from "../../github/client.ts";

type R = Record<string, any>;
export const BILLING_DISCLAIMER_MARKER = "<!-- billing-blocked-disclaimer -->";
const MAX_FILES = 100;
// Secret-bearing files must not be tracked (outside test/fixture folders); without CI that check never runs, so do it here.
const FORBIDDEN_FILE = /(^|\/)\.env$|(^|\/)\.env\.(local|production|prod|staging|dev)$|(^|\/)id_rsa$|(^|\/).+\.pem$|(^|\/).+\.key$/;
const TEST_DIR = /(^|\/)(tests?|fixtures?|spec|examples?|mocks?)\//;

export const isForbiddenFile = (p: string) => FORBIDDEN_FILE.test(p) && !TEST_DIR.test(p);
/** True when at least one check was refused for billing reasons. */
export const isBillingBlocked = (status: R) => !!status.billing_checks?.length;
export const addedLinesOf = (patch: string) => patch.split(/\r?\n/).filter((l) => l.startsWith("+") && !l.startsWith("+++")).map((l) => l.slice(1)).join("\n");

/** Credential scan over the lines a PR adds (no clone needed). Never returns values. */
export async function scanAddedLines(gh: GithubClient, pr: PR): Promise<R[]> {
  const findings: R[] = [], addedByFile = new Map<string, string>();
  for (const f of (await gh.getFiles(pr.base.repo.full_name, pr.number)).slice(0, MAX_FILES)) {
    if (f.status !== "removed" && isForbiddenFile(f.filename)) findings.push({ file: f.filename, rule_id: "forbidden-secret-file", line: 0 });
    const added = addedLinesOf(f.patch ?? "");
    if (added) addedByFile.set(f.filename, added);
    for (const hit of scanText(added)) findings.push({ file: f.filename, rule_id: hit.rule_id, line: hit.line });
  }
  const seen = new Set(findings.map((x) => `${x.file}:${x.line}`));
  return [...findings, ...(await deepScan(addedByFile, seen))];
}

/** Same gitleaks/trufflehog/semgrep/trivy layers as the push guard on the materialised added lines (optional, fail-open). */
async function deepScan(added: Map<string, string>, seen: Set<string>): Promise<R[]> {
  if (!added.size) return [];
  const tmp = mkdtempSync(join(tmpdir(), "pr-added-"));
  try {
    const root = resolve(tmp);
    for (const [name, text] of added) {
      const target = resolve(root, name);
      if (!target.startsWith(root + sep)) continue; // path traversal guard
      mkdirSync(dirname(target), { recursive: true }); writeFileSync(target, text);
    }
    return (await scanClone(root)).filter((h) => !seen.has(`${h.file}:${h.line}`));
  } catch { return []; } finally { rmSync(tmp, { recursive: true, force: true }); }
}

export function buildDisclaimer(billingChecks: string[], sha: string): string {
  const names = billingChecks.slice(0, 10).map((c) => `\`${c}\``).join(", ") || "—";
  return [BILLING_DISCLAIMER_MARKER, "## ⚠️ Pipeline não executada (billing do GitHub Actions)\n",
    `Os checks ${names} **não rodaram** no commit \`${sha.slice(0, 7)}\`: o GitHub Actions recusou iniciar os jobs por limite de gasto/pagamento da conta (comum em repositórios privados). Isso **não é uma falha do código**.\n`,
    "Este PR foi mesclado pelo bot **sem CI**, com base apenas em: sem conflitos, sem credenciais nas linhas adicionadas e aprovação da análise automática.",
    "Recomenda-se rodar a pipeline/testes localmente ou após regularizar o billing."].join("\n");
}
export const hasDisclaimer = (comments: R[]) => comments.some((c) => (c.body ?? "").includes(BILLING_DISCLAIMER_MARKER));
