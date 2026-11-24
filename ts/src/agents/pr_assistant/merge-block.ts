/** Labels the owner uses to hold a PR: any of them blocks every merge path, owner `/merge` included (remove the label to merge). */
import type { PR } from "../../github/client.ts";

const MERGE_BLOCK_LABELS = new Set(["auto-merge-skip", "do-not-merge", "dont-merge", "wip", "work-in-progress"]);
// "DO NOT MERGE", "do_not_merge", "don't merge" all normalise to the kebab form.
const normalise = (name: string) => name.toLowerCase().replace(/['’]/g, "").trim().replace(/[\s_]+/g, "-");

/** The first hold label on the PR, as written on GitHub, or null. */
export function mergeBlockLabel(pr: PR): string | null {
  for (const l of pr.labels ?? []) {
    const name = typeof l === "string" ? l : l?.name ?? "";
    if (MERGE_BLOCK_LABELS.has(normalise(name))) return name;
  }
  return null;
}
