/** Post-model refinement shared by the clone and diff-only reviews: ground → verify → decide. Never throws. */
import { readFileSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";
import type { GithubClient, PR } from "../../github/client.ts";
import { getLogger } from "../../utils/logger.ts";
import { groundFindings, type ReadFile } from "./review-grounding.ts";
import { decide, type ReviewVerdict } from "./review-verdict.ts";
import { verifyFindings, type Ask } from "./review-verify.ts";

const log = getLogger("review");
const MAX_FILE_BYTES = 1_000_000;

/** Read a repo file from the clone; null outside the clone, missing, or too big. */
export function cloneReader(dir: string): ReadFile {
  const root = resolve(dir);
  return (path) => {
    try {
      const full = resolve(root, path);
      if (!full.startsWith(root + sep) || statSync(full).size > MAX_FILE_BYTES) return null;
      return readFileSync(full, "utf8");
    } catch { return null; }
  };
}
/** Per-file patches straight from the GitHub API (three-dot, so only what the PR really changes). */
export async function prSections(gh: GithubClient, pr: PR): Promise<Record<string, string>> {
  const files = await gh.getFiles(pr.base.repo.full_name, pr.number);
  return Object.fromEntries(files.map((f: any) => [f.filename, f.patch ?? ""]));
}
/** Merge-base SHA of the PR, so the local diff never shows the base branch's newer commits as if the PR had reverted them. */
export async function mergeBaseSha(gh: GithubClient, pr: PR): Promise<string> {
  try {
    const sha = (await gh.compare(pr.base.repo.full_name, pr.base.sha ?? pr.base.ref, pr.head.sha))?.merge_base_commit?.sha;
    return typeof sha === "string" && /^[0-9a-f]{40}$/.test(sha) ? sha : "";
  } catch { return ""; }
}
export async function refine(pr: PR, v: ReviewVerdict, sections: Record<string, string>, readFile: ReadFile, ask: Ask): Promise<ReviewVerdict> {
  if (!v.findings.length || !Object.keys(sections).length) return v;
  try {
    const grounded = groundFindings(v.findings, sections, readFile);
    const checked = await verifyFindings(pr.title, grounded.findings, sections, ask);
    const dropped = [...grounded.dropped, ...checked.dropped];
    for (const d of dropped) log.info(`PR #${pr.number}: finding dropped (${d.reason}) — ${d.finding.file}: ${d.finding.issue.slice(0, 120)}`);
    return decide({ ...v, findings: checked.findings }, dropped.length);
  } catch (e) { log.warning(`review refinement failed for PR #${pr.number}: ${(e as Error).name}`); return v; }
}
