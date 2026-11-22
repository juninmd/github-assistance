/**
 * When no review model answers, the merge may go on without model review, but only in tiers: the failure must persist
 * across runs (a pending notice first), the diff must be small and a per-run cap applies. Infra errors never get here.
 */
export const WAIVER_MARKER = "<!-- pr-assistant:review-waived -->";
export const PENDING_MARKER = "<!-- pr-assistant:review-waiver-pending -->";
const int = (v: string | undefined, d: number) => { const n = parseInt(v ?? "", 10); return Number.isNaN(n) ? d : Math.max(0, n); };
export const waiverEnabled = (v = process.env.REVIEW_WAIVE_ON_FAILURE) => !["0", "false", "no", "off"].includes((v ?? "").trim().toLowerCase());
export const waiveAfterMinutes = () => int(process.env.REVIEW_WAIVE_AFTER_MINUTES, 30);
export const waiveMaxLines = () => int(process.env.REVIEW_WAIVE_MAX_LINES, 500);
export const waiveMaxPerRun = () => int(process.env.REVIEW_WAIVE_MAX_PER_RUN, 3);

const tag = (sha: string) => `\`${sha.slice(0, 8)}\``;
const forSha = (comments: any[], marker: string, sha: string) => comments.filter((c) => (c.body ?? "").includes(marker) && (c.body ?? "").includes(tag(sha)));
export const hasWaiver = (comments: any[], sha: string) => forSha(comments, WAIVER_MARKER, sha).length > 0;
/** When the first "review unavailable" notice for this SHA was posted (ms), or null. */
export function pendingSince(comments: any[], sha: string): number | null {
  const ts = forSha(comments, PENDING_MARKER, sha).map((c) => Date.parse(c.created_at ?? "")).filter((t) => !Number.isNaN(t));
  return ts.length ? Math.min(...ts) : null;
}
export type WaiverStep = "pending" | "wait" | "waive" | "too_large" | "cap";
export function decideWaiver(pr: any, comments: any[], waivedThisRun: number, now = Date.now()): WaiverStep {
  const sha = pr.head?.sha ?? "";
  if (hasWaiver(comments, sha)) return "waive";
  if ((pr.additions ?? 0) + (pr.deletions ?? 0) > waiveMaxLines()) return "too_large";
  if (waivedThisRun >= waiveMaxPerRun()) return "cap";
  const after = waiveAfterMinutes();
  if (after === 0) return "waive";
  const since = pendingSince(comments, sha);
  if (since === null) return "pending";
  return now - since >= after * 60_000 ? "waive" : "wait";
}
export function pendingComment(sha: string, why: string): string {
  return [PENDING_MARKER, "## ⏳ Revisão automática indisponível",
    `Nenhum modelo concluiu a revisão (${why.slice(0, 200)}). Vou tentar de novo nas próximas rodadas; se continuar indisponível por ${waiveAfterMinutes()} min e o diff for pequeno, o merge segue sem revisão por modelo.`,
    `<sub>SHA ${tag(sha)}</sub>`].join("\n\n");
}
export function waiverComment(sha: string, why: string): string {
  return [WAIVER_MARKER, "## ⚠️ Revisão automática pulada",
    `Nenhum modelo conseguiu concluir a revisão deste PR (${why.slice(0, 200)}) por mais de ${waiveAfterMinutes()} min. A varredura de credenciais nas linhas adicionadas continua valendo; o merge segue sem a revisão por modelo.`,
    `<sub>SHA ${tag(sha)}</sub>`].join("\n\n");
}
