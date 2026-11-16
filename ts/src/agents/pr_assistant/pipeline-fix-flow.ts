/** On a failing pipeline, attempt a bounded autonomous fix (attempts tracked via marker comments); best-effort, never throws. */
import type { GithubClient, PR } from "../../github/client.ts";
import { commitsBehind } from "./branch-staleness.ts";
import { getPipelineErrorLogs } from "./logs.ts";
import { checkPipelineStatus } from "./pipeline.ts";
import { MANUAL_PIPELINE_LABEL, buildMarker, fixPipelineAutonomously, maxAttempts, pipelineFixEnabled, readAttemptState } from "./pipeline-fixer.ts";

type Log = (m: string, level?: string) => void;

async function commentAttempt(pr: PR, gh: GithubClient, log: Log, msg: string, attempt: number, mx: number, sha: string, success: boolean) {
  const author = pr.user?.login ?? "contributor";
  const outcome = success ? "apliquei uma correção automática no pipeline" : "tentei corrigir o pipeline, mas a tentativa falhou";
  const body = `**Tentativa ${attempt}/${mx} de corrigir o pipeline**\n\nOlá @${author}, ${outcome}.\n\n**Detalhes:** ${msg}\n\n${buildMarker(attempt, sha)}`;
  try { await gh.commentOnPr(pr, body); } catch (e) { log(`Failed to comment pipeline attempt on PR #${pr.number}: ${e}`, "WARNING"); }
}
async function markManual(pr: PR, gh: GithubClient, log: Log, reason: string) {
  try { await gh.addLabelToPr(pr, MANUAL_PIPELINE_LABEL); log(`PR #${pr.number} marked ${MANUAL_PIPELINE_LABEL}: ${reason}`, "WARNING"); }
  catch (e) { log(`Failed to label PR #${pr.number}: ${e}`, "WARNING"); }
}
export const updateStaleBranchEnabled = () => ["1", "true", "yes", "on"].includes((process.env.PIPELINE_FIX_UPDATE_BRANCH ?? "true").toLowerCase());
async function commentBranchUpdate(pr: PR, gh: GithubClient, log: Log, behind: number, baseRef: string) {
  const body = "**Pipeline: branch desatualizado**\n\n" +
    `O PR estava **${behind}** commit(s) atrás de \`${baseRef}\`. O CI valida um merge ` +
    "desatualizado, que pode falhar sem existir erro no código deste PR — nenhuma edição de arquivo resolveria.\n\n" +
    `**Ação:** atualizei o branch a partir de \`${baseRef}\`. O CI vai rodar de novo.`;
  try { await gh.commentOnPr(pr, body); } catch (e) { log(`Failed to comment branch update on PR #${pr.number}: ${e}`, "WARNING"); }
}
async function tryUpdateStaleBranch(pr: PR, gh: GithubClient, log: Log): Promise<boolean> {
  if (!updateStaleBranchEnabled()) return false;
  const behind = await commitsBehind(gh, pr);
  if (behind <= 0) return false;
  const baseRef = pr.base?.ref || "base";
  log(`PR #${pr.number}: failing on a branch ${behind} commit(s) behind ${baseRef} — updating`);
  try {
    const [updated, msg] = await gh.updatePrBranch(pr);
    if (!updated) { log(`update-branch rejected on PR #${pr.number}: ${msg}`, "WARNING"); return false; }
  } catch (e) { log(`update-branch failed on PR #${pr.number}: ${e}`, "WARNING"); return false; }
  await commentBranchUpdate(pr, gh, log, behind, baseRef);
  return true;
}
/** One bounded autonomous pipeline fix; true when a fix was pushed. */
export async function attemptPipelineFix(pr: PR, gh: GithubClient, log: Log): Promise<boolean> {
  if (!pipelineFixEnabled()) return false;
  try {
    const status = await checkPipelineStatus(gh, pr);
    if (!["failure", "error"].includes(status.state)) return false;
    if (await tryUpdateStaleBranch(pr, gh, log)) return true;
    const comments = await gh.getIssueComments(pr.base.repo.full_name, pr.number);
    const [last] = readAttemptState(comments);
    const mx = maxAttempts();
    if (last >= mx) { await markManual(pr, gh, log, `still failing after ${last} attempts`); return false; }
    const data = await getPipelineErrorLogs(gh, pr);
    if (!data.logs.trim()) { log(`No actionable pipeline logs for PR #${pr.number}`, "WARNING"); return false; }
    const attempt = last + 1;
    log(`PR #${pr.number}: pipeline failing — fix attempt ${attempt}/${mx}`);
    const [success, msg, sha] = await fixPipelineAutonomously(gh, pr, data.logs, data.failed_checks, attempt, mx);
    await commentAttempt(pr, gh, log, msg, attempt, mx, sha || pr.head.sha, success);
    if (success) return true;
    if (attempt >= mx) await markManual(pr, gh, log, msg);
    return false;
  } catch (e) { log(`Pipeline fix attempt failed for PR #${pr.number}: ${e}`, "WARNING"); return false; }
}
