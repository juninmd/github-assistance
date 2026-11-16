/**
 * Blocks a PR whose added lines contain credential-like content (critical REQUEST_CHANGES → draft + failing status until a new
 * commit removes it). Scans only lines the PR adds; findings never include the secret value.
 */
import { scanText } from "../../utils/secret-scan.ts";
import type { GithubClient, PR } from "../../github/client.ts";
import { mkFinding, mkVerdict, REQUEST_CHANGES, type ReviewVerdict } from "./review-verdict.ts";
import { addedLinesOf } from "./billing-gate.ts";

export const MODEL_LABEL = "credential-scan";
export const addedLines = addedLinesOf;
/** Added lines across every changed file of the PR, uncapped. */
export async function prAddedText(gh: GithubClient, pr: PR): Promise<string> {
  const parts: string[] = [];
  for (const f of await gh.getFiles(pr.base.repo.full_name, pr.number)) if (f.patch) parts.push(addedLines(f.patch));
  return parts.join("\n");
}
/** Critical verdict when `text` contains credential-like content, else null. */
export function credentialVerdict(text: string): ReviewVerdict | null {
  const findings = scanText(text, { env: {} });
  if (!findings.length) return null;
  return mkVerdict({
    verdict: REQUEST_CHANGES, summary: "PR bloqueado: possível credencial exposta nas linhas adicionadas.", model: MODEL_LABEL,
    findings: findings.map((i) => mkFinding({ file: "(diff)", line: Number(i.line), severity: "error", issue: `Possível credencial exposta (${i.rule_id}). Remova o valor do código, revogue a credencial no provedor e use variável de ambiente ou secret.` })),
  });
}
