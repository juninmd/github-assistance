/** Queryable view over why a PR was not merged (CLI/API). */
import { AutonomyPolicy } from "../config/autonomy.ts";
import type { Settings } from "../config/settings.ts";
import { GithubClient } from "../github/client.ts";
import { MergePolicy } from "../agents/pr_assistant/merge-policy.ts";
import { checkPipelineStatus } from "../agents/pr_assistant/pipeline.ts";
import { listJobs } from "../queue/read.ts";
import { JobStore } from "../queue/store.ts";

/** Durable job history for a PR (or the most recent jobs); filtered in SQL so old PRs are not hidden by `limit`. */
export function jobHistory(s: Pick<Settings, "webhookDatabasePath">, prRef?: string | null, limit = 50) {
  new JobStore(s.webhookDatabasePath).initialize();
  return listJobs(s.webhookDatabasePath, { kind: "pr", key: prRef ?? undefined, limit });
}
export async function explainPr(s: Settings, prRef: string, gh?: GithubClient): Promise<Record<string, any>> {
  const repo = prRef.split("#", 1)[0]!;
  const number = parseInt(prRef.split("#").pop() ?? "", 10);
  if (!prRef.includes("#") || Number.isNaN(number)) return { pr_ref: prRef, reasons: ["invalid_pr_ref"] };
  const autonomy = new AutonomyPolicy(s.autonomyPolicyPath).forRepository(repo);
  const history = jobHistory(s, prRef);
  let pr: any, client: GithubClient;
  try { client = gh ?? new GithubClient(s.githubToken); pr = await client.getPull(repo, number); }
  catch (e: any) { return { pr_ref: prRef, reasons: [`pr_unavailable: ${e?.message ?? e}`], autonomy_mode: autonomy.mode, job_history: history }; }
  const status = await checkPipelineStatus(client, pr);
  const decision = new MergePolicy().evaluate({ status, expectedSha: null, currentSha: pr.head.sha, autonomy });
  const reasons = [...decision.reasons];
  if (pr.mergeable === false) reasons.push("merge_conflicts");
  if (pr.merged_at) reasons.push("already_merged");
  return { pr_ref: prRef, state: pr.state, merged: !!pr.merged_at, head_sha: pr.head.sha, autonomy_mode: autonomy.mode, pipeline_state: status.state, reasons, decision: decision.action, job_history: history };
}
