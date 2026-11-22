/**
 * Light lane for dependency bots (dependabot/renovate): no model review, but the added lines are scanned for credentials,
 * only dependency files may change, and at least one real (non-advisory, non-billing) check must pass; otherwise, when
 * Actions are billing-blocked, the same scan + disclaimer path as any other PR applies.
 */
import type { GithubClient, PR } from "../../github/client.ts";
import { scanAddedLines } from "./billing-gate.ts";
import { isLockfile } from "./conflict-plan.ts";

type R = Record<string, any>;
export const isDependencyBot = (login?: string | null) => /^(app\/)?(dependabot|renovate)(\[bot\])?$/i.test((login ?? "").trim());
export const isDependabot = (login?: string | null) => /^(app\/)?dependabot(\[bot\])?$/i.test((login ?? "").trim());

const MANIFEST = /(^|\/)(package\.json|requirements[^/]*\.(txt|in)|pyproject\.toml|setup\.(cfg|py)|Pipfile|go\.mod|Cargo\.toml|Gemfile|[^/]+\.gemspec|composer\.json|pom\.xml|build\.gradle(\.kts)?|gradle\.properties|libs\.versions\.toml|[^/]+\.(csproj|fsproj|vbproj)|Directory\.Packages\.props|packages\.config|global\.json|pubspec\.yaml|mix\.exs|Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose\.ya?ml|[^/]+\.tf|\.terraform\.lock\.hcl|\.gitmodules|\.tool-versions|\.nvmrc|\.python-version|action\.ya?ml)$/i;
const WORKFLOW = /^\.github\/(workflows|actions)\//;
export const isDependencyFile = (path: string) => MANIFEST.test(path) || WORKFLOW.test(path) || isLockfile(path);

/** Checks that really ran and passed: advisory bots and billing-refused jobs prove nothing about the code. */
export function realPassedChecks(status: R): number {
  const ignore = new Set([...(status.advisory_checks ?? []), ...(status.billing_checks ?? [])]);
  return (status.success_checks ?? []).filter((c: R) => !ignore.has(c.context)).length;
}
export type LaneResult = { ok: boolean; reason: string };
export async function laneCheck(gh: GithubClient, pr: PR): Promise<LaneResult> {
  let files: R[];
  try { files = await gh.getFiles(pr.base.repo.full_name, pr.number); } catch (e) { return { ok: false, reason: `dependency_lane_unavailable: ${e}` }; }
  const odd = files.map((f) => f.filename as string).filter((f) => !isDependencyFile(f));
  if (odd.length) return { ok: false, reason: `dependency_lane_unexpected_files: ${odd.slice(0, 5).join(", ")}` };
  const leaks = await scanAddedLines(gh, pr, files);
  if (leaks.length) return { ok: false, reason: `dependency_lane_credential_found: ${leaks.slice(0, 3).map((h) => `${h.file}:${h.line}`).join("; ")}` };
  return { ok: true, reason: "dependency_lane_ok" };
}
/** Lane decision for a dependency-bot PR whose review was skipped: merge with real green checks, or billing-blocked with a clean scan. */
export async function laneAllowsMerge(gh: GithubClient, pr: PR, status: R): Promise<LaneResult> {
  const billing = (status.billing_checks?.length ?? 0) > 0;
  if (status.state !== "success") return { ok: false, reason: "dependency_checks_not_green" };
  if (!billing && realPassedChecks(status) === 0) return { ok: false, reason: "dependency_no_real_checks" };
  return laneCheck(gh, pr);
}

export const REBASE_COMMAND = "@dependabot rebase";
const REBASE_COOLDOWN_MS = 6 * 60 * 60_000;
/** Ask dependabot to rebase its own branch (pushing to it would make dependabot stop updating the PR). Once per 6h. */
export async function requestDependabotRebase(gh: GithubClient, pr: PR, comments: R[], now = Date.now()): Promise<boolean> {
  const recent = comments.some((c) => (c.body ?? "").trim().startsWith(REBASE_COMMAND) && now - Date.parse(c.created_at ?? "") < REBASE_COOLDOWN_MS);
  if (recent) return false;
  try { await gh.commentOnPr(pr, REBASE_COMMAND); return true; } catch { return false; }
}
