/** Static analysis (gitleaks, trufflehog, trivy, semgrep) on the PR clone; findings on lines the PR adds join the review. */
import { gitleaksEnabled, gitleaksScan } from "../../utils/secret-scan.ts";
import { sastScan } from "../../utils/sast-scan.ts";
import { run } from "../../utils/proc.ts";
import { getLogger } from "../../utils/logger.ts";
import { parseDiff } from "./review-lines.ts";
import { enabled } from "./review-flags.ts";
import { mkFinding, mkVerdict, REQUEST_CHANGES, type Finding, type ReviewVerdict } from "./review-verdict.ts";

const log = getLogger("review");
export const SAST_MODEL = "sast";
export const sastReviewEnabled = () => enabled("REVIEW_SAST_ENABLED", true);
type Raw = { file?: string; rule_id: string; line: number };
const SECRET = /^(gitleaks|trufflehog):|^trivy:.*(secret|key|token)/i;

/** Pure: keep findings on added lines, secrets as `error` (block), the rest `warn`. Never carries the secret value. */
export function toFindings(raw: Raw[], added: Map<string, Set<number>>): Finding[] {
  const seen = new Set<string>(), out: Finding[] = [];
  for (const r of raw) {
    const file = r.file ?? "", k = `${file}:${r.line}:${r.rule_id}`;
    if (!file || !r.line || !added.get(file)?.has(r.line) || seen.has(k)) continue;
    seen.add(k);
    const secret = SECRET.test(r.rule_id);
    out.push(mkFinding({ file, line: r.line, severity: secret ? "error" : "warn",
      issue: secret ? `Análise estática (${r.rule_id}): possível credencial. Remova do código, revogue no provedor e use secret/variável de ambiente.`
        : `Análise estática (${r.rule_id}): achado de segurança em linha alterada por este PR.` }));
  }
  return out;
}
/** Fail-open: a broken scanner never blocks the review. */
export async function prSastFindings(dir: string, baseRef: string): Promise<Finding[]> {
  if (!sastReviewEnabled()) return [];
  try {
    const diff = await run(["git", "diff", "--unified=0", `origin/${baseRef}`, "HEAD"], { cwd: dir, timeoutMs: 60_000 });
    if (diff.code !== 0) return [];
    const added = parseDiff(diff.stdout), files = new Set(added.keys());
    if (!files.size) return [];
    const raw: Raw[] = [...(await sastScan(dir, files))];
    if (gitleaksEnabled()) raw.push(...(await gitleaksScan(dir)));
    return toFindings(raw, added);
  } catch (e) { log.warning(`sast scan failed: ${(e as Error).name}`); return []; }
}
const MAX_PROMPT_FINDINGS = 30;
/** Pure: SAST context for the opencode prompt (type, file, line; never the matched value). */
export function promptBlock(found: Finding[]): string {
  if (!found.length) return "";
  const rows = found.slice(0, MAX_PROMPT_FINDINGS).map((f) => `- \`${f.file}\` linha ${f.line} (${f.severity}): ${f.issue}`);
  return "Análise estática (gitleaks/trufflehog/trivy/semgrep) já rodou neste PR. Estes achados já serão anexados ao veredito, " +
    "não os repita como findings; use-os para focar a revisão e diga no `summary` se algum parecer falso positivo:\n" +
    `${rows.join("\n")}\n`;
}
/** Adds SAST findings to a verdict; with no model verdict, only a blocking secret produces one. */
export function mergeSast(v: ReviewVerdict | null, found: Finding[]): ReviewVerdict | null {
  if (!found.length) return v;
  const blocking = found.some((f) => f.severity === "error");
  const note = `Análise estática: ${found.length} achado(s) em linhas deste PR.`;
  if (!v) return blocking ? mkVerdict({ verdict: REQUEST_CHANGES, summary: note, findings: found, model: SAST_MODEL }) : null;
  return { ...v, verdict: blocking ? REQUEST_CHANGES : v.verdict, summary: `${v.summary} ${note}`.trim(), findings: [...v.findings, ...found] };
}
