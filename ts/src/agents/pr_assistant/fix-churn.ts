/** Whitespace-only churn in an automated fix: re-indenting a file to change one line breaks formatters and hides the real edit. */
import { run } from "../../utils/proc.ts";

export const MAX_WHITESPACE_LINES = 20;
const sum = (numstat: string) => numstat.split(/\r?\n/).reduce((n, l) => {
  const [a, d] = l.split("\t");
  return n + (parseInt(a ?? "", 10) || 0) + (parseInt(d ?? "", 10) || 0);
}, 0);
/** Changed lines in total and those that only differ by whitespace; `cached` reads the index instead of the worktree. */
export async function whitespaceChurn(dir: string, cached = false): Promise<{ total: number; whitespace: number }> {
  const base = ["git", "diff", ...(cached ? ["--cached"] : []), "--numstat"];
  const total = sum((await run(base, { cwd: dir, timeoutMs: 30_000 })).stdout);
  const real = sum((await run([...base, "-w", "--ignore-blank-lines"], { cwd: dir, timeoutMs: 30_000 })).stdout);
  return { total, whitespace: Math.max(0, total - real) };
}
/** Reason to reject, or "" when the whitespace churn is small or not most of the diff. */
export async function churnReason(dir: string, cached = false): Promise<string> {
  const { total, whitespace } = await whitespaceChurn(dir, cached);
  return whitespace >= MAX_WHITESPACE_LINES && whitespace * 2 > total
    ? `${whitespace} of ${total} changed lines are whitespace-only (re-indent/reformat); change only the lines the fix needs` : "";
}
