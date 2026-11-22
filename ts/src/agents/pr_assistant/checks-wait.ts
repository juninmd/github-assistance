/**
 * Review starts only after every check of the head SHA finished (required or not). Absent checks never wait (no CI,
 * billing-blocked Actions); jobs stuck pending past CHECKS_WAIT_MAX_MINUTES since the head commit stop blocking.
 */
const int = (v: string | undefined, d: number) => { const n = parseInt(v ?? "", 10); return Number.isNaN(n) ? d : Math.max(0, n); };
export const checksWaitEnabled = (v = process.env.CHECKS_WAIT_ENABLED) => !["0", "false", "no", "off"].includes((v ?? "").trim().toLowerCase());
export const checksWaitMaxMinutes = () => int(process.env.CHECKS_WAIT_MAX_MINUTES, 45);

/** True while the PR must keep waiting. `headAt` = head commit time (ms); unknown time waits (next run re-checks). */
export function mustWaitForChecks(status: Record<string, any>, headAt: number | null, now = Date.now()): boolean {
  if (!checksWaitEnabled() || status.state !== "pending" || !(status.pending_checks?.length)) return false;
  return headAt === null || now - headAt < checksWaitMaxMinutes() * 60_000;
}
