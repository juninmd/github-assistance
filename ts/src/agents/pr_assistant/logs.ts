/** Collect failed GitHub Actions logs / check-run annotations for the AI fixer. */
import type { GithubClient, PR } from "../../github/client.ts";

type R = Record<string, any>;
const LOG_TIMESTAMP_RE = /^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s/;
const ANSI_RE = /\x1b\[[0-9;]*m/g;
// Runner/security-agent journal noise that buries the real error (e.g. harden-runner dumps its whole journal during post-job cleanup).
const LOG_NOISE_RE = /(agentservice\[|systemd\[\d|sudo\[\d|pam_unix\(|module=armour|\[armour-cdr\]|Download action repository|Prepare all required actions|##\[endgroup\]|^\s*\*\s+\[new branch\].*->\s+origin\/)/;
const ERROR_MARKER_RE = /(##\[error\]|\berror\[|\berror:|\bERROR\b|\bFAILED?\b|Traceback|exception|panicked)/i;
const ERROR_CONTEXT_LINES = 25, MAX_LINES_PER_JOB = 200, MAX_LOG_CHARS = 12000, LOG_REQUEST_TIMEOUT_MS = 30_000;
const FAILING = ["failure", "timed_out", "action_required"];

const cleanLogLine = (l: string) => l.replace(ANSI_RE, "").replace(LOG_TIMESTAMP_RE, "").trimEnd();

/** Actual error context from a job log (noise-filtered). */
export function tailJobLog(raw: string): string {
  const lines = raw.split(/\r?\n/).map(cleanLogLine).filter((l) => l && !LOG_NOISE_RE.test(l));
  if (!lines.length) return "";
  const idx = lines.flatMap((l, i) => (ERROR_MARKER_RE.test(l) ? [i] : []));
  if (!idx.length) return lines.slice(-MAX_LINES_PER_JOB).join("\n");
  const keep = new Set<number>();
  for (const i of idx) for (let k = Math.max(0, i - ERROR_CONTEXT_LINES); k < Math.min(lines.length, i + 2); k++) keep.add(k);
  return [...keep].sort((a, b) => a - b).map((i) => lines[i]).slice(-MAX_LINES_PER_JOB).join("\n");
}

async function downloadJobLog(repo: string, jobId: number, token: string): Promise<string | null> {
  try {
    const res = await fetch(`https://api.github.com/repos/${repo}/actions/jobs/${jobId}/logs`, { headers: { Authorization: `token ${token}`, Accept: "application/vnd.github+json" }, signal: AbortSignal.timeout(LOG_REQUEST_TIMEOUT_MS) });
    if (res.status !== 200) return null;
    return (await res.text()) || null;
  } catch { return null; }
}

async function logsFromRuns(gh: GithubClient, repo: string, runs: R[], token: string): Promise<[string[], string[]]> {
  const blocks: string[] = [], names: string[] = [];
  for (const run of runs) {
    let jobs: R[];
    try { jobs = await gh.paginate(`/repos/${repo}/actions/runs/${run.id}/jobs`, { key: "jobs" }); } catch { continue; }
    for (const job of jobs) {
      if (!FAILING.includes(job.conclusion)) continue;
      names.push(job.name || "job");
      const raw = await downloadJobLog(repo, job.id, token); if (!raw) continue;
      const tail = tailJobLog(raw); if (tail) blocks.push(`### Job: ${job.name}\n${tail}`);
    }
  }
  return [blocks, names];
}

const summaryOf = (cr: R) => (cr.output && typeof cr.output === "object" ? cr.output.summary : null) || "No details";

/** Fallback: error context from check-run summaries and annotations. */
async function logsFromCheckRuns(gh: GithubClient, pr: PR): Promise<[string[], string[]]> {
  const blocks: string[] = [], names: string[] = [];
  let runs: R[];
  try { runs = await gh.getCheckRuns(pr.base.repo.full_name, pr.head.sha); } catch { return [blocks, names]; }
  for (const cr of runs) {
    if (!FAILING.includes(cr.conclusion)) continue;
    names.push(cr.name || "check");
    const parts = [`### Check: ${cr.name}`, summaryOf(cr)];
    let anns: R[] = [];
    try { anns = await gh.paginate(`/repos/${pr.base.repo.full_name}/check-runs/${cr.id}/annotations`, { limit: 30 }); } catch { anns = []; }
    for (const a of anns.slice(0, 30)) parts.push(`${a.path || ""}:${a.start_line || ""} ${a.message || ""}`.trim());
    blocks.push(parts.filter(Boolean).join("\n"));
  }
  return [blocks, names];
}

/** Failed GitHub Actions error logs for the PR head commit. */
export async function getPipelineErrorLogs(gh: GithubClient, pr: PR, token?: string | null): Promise<{ logs: string; failed_checks: string[] }> {
  token = token || process.env.GITHUB_TOKEN || process.env.GH_PAT || "";
  let blocks: string[] = [], names: string[] = [];
  try {
    const repo = pr.base.repo.full_name;
    const runs = (await gh.paginate(`/repos/${repo}/actions/runs?head_sha=${pr.head.sha}`, { key: "workflow_runs" })).filter((r) => FAILING.includes(r.conclusion));
    if (token && runs.length) [blocks, names] = await logsFromRuns(gh, repo, runs, token);
  } catch { blocks = []; names = []; }
  if (!blocks.length) { const [fb, fn] = await logsFromCheckRuns(gh, pr); blocks = fb; names = names.length ? names : fn; }
  let logs = blocks.join("\n\n");
  if (logs.length > MAX_LOG_CHARS) logs = logs.slice(-MAX_LOG_CHARS);
  return { logs, failed_checks: [...new Set(names)] };
}
