/** Route GitHub webhook events to durable PR automation jobs. */
import { Priorities } from "../config/priorities.ts";
import type { Settings } from "../config/settings.ts";
import { JobStore } from "../queue/store.ts";
import type { Job } from "../queue/schema.ts";
import type { Handler } from "../queue/worker.ts";
import { getLogger } from "../utils/logger.ts";
import { GitHubAppAuth } from "./auth.ts";

const TRANSIENT = ["mergeable_state_unknown", "refresh_failed"];
const log = getLogger("webhook-dispatcher");
const pullNumbers = (xs: any[] = []) => xs.map((x) => x?.number).filter((n) => Number.isInteger(n)) as number[];

export function extractPrRefs(event: string, payload: Record<string, any>): string[] {
  const repo = payload.repository?.full_name;
  if (!repo) return [];
  const nums = new Set<number>();
  if (event === "pull_request" || event === "pull_request_review") {
    const n = payload.pull_request?.number || payload.number;
    if (Number.isInteger(n)) nums.add(n);
  } else if (event === "issue_comment" && payload.issue?.pull_request) {
    if (Number.isInteger(payload.issue.number)) nums.add(payload.issue.number);
  } else if (event === "check_suite") pullNumbers(payload.check_suite?.pull_requests).forEach((n) => nums.add(n));
  else if (event === "workflow_run") pullNumbers(payload.workflow_run?.pull_requests).forEach((n) => nums.add(n));
  return [...nums].sort((a, b) => a - b).map((n) => `${repo}#${n}`);
}

export function enqueuePr(s: Settings, prRef: string): boolean {
  const store = new JobStore(s.webhookDatabasePath);
  store.initialize();
  const prio = new Priorities(s.prioritiesPath).priorityFor(prRef);
  const [, created] = store.enqueue("pr", prRef, { mode: s.automationMode, source: "manual" }, { priority: prio, repo: prRef.split("#", 1)[0] });
  log.info("PR job enqueued", { pr_ref: prRef, created });
  return true;
}

export type RunAgentFn = (agent: string, settings: Settings, o: { prRef?: string }) => Promise<Record<string, any>>;

export function makePrHandler(s: Settings, runAgent: RunAgentFn, tokenFn?: () => Promise<string>): Handler {
  return async (job: Job) => {
    const mode = job.payload?.mode || s.automationMode;
    if (mode !== "autonomous") return { status: "succeeded", decision: "observed", next_action: "observe" };
    const token = await (tokenFn ?? (() => installationToken(s)))();
    const result = await runAgent("pr-assistant", { ...s, githubToken: token }, { prRef: job.key });
    if (result.error) return { status: "failed", error: String(result.error), decision: "failed", next_action: "retry" };
    const transient = (result.blocked ?? []).map((b: any) => String(b.reason ?? "")).filter((r: string) => TRANSIENT.some((t) => r.startsWith(t)));
    if (transient.length) return { status: "failed", error: `transient block: ${transient.join(", ")}`, decision: "blocked", next_action: "retry" };
    return {
      status: "succeeded", decision: result._run_result?.status || result.status || "succeeded",
      next_action: "done", sha: result.sha, task_id: result.task_id,
    };
  };
}

async function installationToken(s: Settings): Promise<string> {
  if (!(s.githubAppId && s.githubInstallationId && s.githubAppPrivateKeyPath)) throw new Error("GitHub App authentication is incomplete");
  return new GitHubAppAuth(s.githubAppId, s.githubInstallationId, s.githubAppPrivateKeyPath).installationToken();
}
