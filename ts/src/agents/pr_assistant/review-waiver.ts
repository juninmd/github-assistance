/** When no review model answers, the bot says so on the PR (once per head SHA) and lets the merge proceed. */
export const WAIVER_MARKER = "<!-- pr-assistant:review-waived -->";
export const waiverEnabled = (v = process.env.REVIEW_WAIVE_ON_FAILURE) => !["0", "false", "no", "off"].includes((v ?? "").trim().toLowerCase());
export const hasWaiver = (comments: any[], sha: string) => comments.some((c) => (c.body ?? "").includes(WAIVER_MARKER) && (c.body ?? "").includes(`\`${sha.slice(0, 8)}\``));
export function waiverComment(sha: string, why: string): string {
  return [WAIVER_MARKER, "## ⚠️ Revisão automática pulada",
    `Nenhum modelo conseguiu concluir a revisão deste PR (${why.slice(0, 200)}). A varredura de credenciais e o SAST continuam valendo; o merge segue sem a revisão por modelo.`,
    `<sub>SHA \`${sha.slice(0, 8)}\`</sub>`].join("\n\n");
}
