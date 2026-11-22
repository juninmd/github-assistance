/** Destructive automated fixes: a review fix once replaced 155 lines of zplint's src/fix.rs with 15 (zplint#44). */
import { run } from "../../utils/proc.ts";

/** A file loses at least this many lines and over GUT_RATIO times what it gains: the fix rewrote it, not patched it. */
export const MIN_GUTTED_LINES = 40;
export const GUT_RATIO = 4;

const diff = (dir: string, cached: boolean, extra: string[]) =>
  run(["git", "diff", ...(cached ? ["--cached"] : []), ...extra], { cwd: dir, timeoutMs: 30_000 });

/** Reason to reject, or "" when the fix keeps every tracked file and only trims code in proportion. */
export async function deletionReason(dir: string, cached = false): Promise<string> {
  const removed = (await diff(dir, cached, ["--diff-filter=D", "--name-only"])).stdout.split(/\r?\n/).filter(Boolean);
  if (removed.length) return `the fix deletes tracked file(s) ${removed.slice(0, 8).join(", ")}; fixes must edit code, never remove files`;
  const gutted: string[] = [];
  for (const line of (await diff(dir, cached, ["--numstat"])).stdout.split(/\r?\n/)) {
    const [a, d, file] = line.split("\t");
    const added = parseInt(a ?? "", 10), deleted = parseInt(d ?? "", 10);
    // Binary files report "-": nothing to judge line-wise.
    if (!file || Number.isNaN(added) || Number.isNaN(deleted)) continue;
    if (deleted >= MIN_GUTTED_LINES && deleted > added * GUT_RATIO) gutted.push(`${file} (-${deleted}/+${added})`);
  }
  return gutted.length
    ? `the fix removes far more code than it adds in ${gutted.slice(0, 8).join(", ")}; change only the lines the finding needs`
    : "";
}
