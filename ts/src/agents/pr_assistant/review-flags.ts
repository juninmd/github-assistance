/** Runtime flags shared by the advisory PR review pipeline ("review by default, enforced, but safe to dry-run"). */
const FALSEY = new Set(["0", "false", "no", "off"]);
export function enabled(name: string, def = false): boolean {
  const raw = process.env[name];
  return raw === undefined || !raw.trim() ? def : !FALSEY.has(raw.trim().toLowerCase());
}
/** When true, reviews run end-to-end but write nothing (no comment, label, status or autofix push). */
export const reviewDryRun = () => enabled("REVIEW_DRY_RUN", false);
/** Lowest finding severity that blocks the merge via the review gate. */
export const gateMinSeverity = () => (process.env.REVIEW_GATE_MIN_SEVERITY ?? "").trim().toLowerCase() || "error";
