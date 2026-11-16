/** Jules v1alpha REST client (https://jules.google/docs/api/reference/). Auth via X-Goog-Api-Key. */
import { HttpError, withRetry } from "../utils/retry.ts";
import { getLogger } from "../utils/logger.ts";

const log = getLogger("jules");
const envInt = (n: string, d: number, min = 1) => { const v = parseInt(process.env[n] ?? "", 10); return Number.isNaN(v) ? d : Math.max(min, v); };
const TIMEOUT = () => envInt("JULES_TIMEOUT_SECONDS", 300) * 1000;
const WAIT = () => envInt("JULES_WAIT_SECONDS", 14400);
const ATTEMPTS = () => envInt("JULES_RETRY_ATTEMPTS", 3);
const MAX_PAGES = () => envInt("JULES_MAX_ACTIVITY_PAGES", 50);
const MAX_ACTIVITIES = () => envInt("JULES_MAX_ACTIVITIES", 500);
const RETRYABLE = new Set([429, 500, 502, 503, 504]);
const retryable = (e: unknown) => (e instanceof HttpError && RETRYABLE.has(e.status)) || (e instanceof Error && ["TimeoutError", "TypeError"].includes(e.name));
const createRetryable = (e: unknown) => e instanceof HttpError && e.status === 429;

export class JulesClient {
  static BASE_URL = "https://jules.googleapis.com";
  apiKey: string | null;
  constructor(apiKey?: string | null, private base = JulesClient.BASE_URL) {
    this.apiKey = apiKey || process.env.JULES_API_KEY || null;
    if (!this.apiKey) log.warning("Jules API key is missing (JULES_API_KEY). Jules features will not work.");
  }
  private async call(method: string, path: string, o: { body?: unknown; params?: Record<string, unknown>; timeoutMs?: number; allow404?: boolean } = {}): Promise<any> {
    const qs = o.params ? "?" + new URLSearchParams(Object.entries(o.params).map(([k, v]) => [k, String(v)])).toString() : "";
    const res = await fetch(`${this.base}/v1alpha/${path}${qs}`, {
      method, headers: { "X-Goog-Api-Key": this.apiKey ?? "", "Content-Type": "application/json" },
      body: o.body !== undefined ? JSON.stringify(o.body) : undefined, signal: AbortSignal.timeout(o.timeoutMs ?? TIMEOUT()),
    });
    if (o.allow404 && res.status === 404) return null;
    if (!res.ok) throw new HttpError(res.status, `Jules ${method} ${path} -> ${res.status}`);
    const t = await res.text();
    return t ? JSON.parse(t) : {};
  }
  private r<T>(fn: () => Promise<T>, base = 1, rt = retryable) { return withRetry(fn, { maxAttempts: ATTEMPTS(), baseDelay: base, retryable: rt }); }

  async listSources(): Promise<any[]> {
    return this.r(async () => { const out: any[] = []; let tok: string | undefined; do { const d = await this.call("GET", "sources", { params: tok ? { pageToken: tok } : {} }); out.push(...(d.sources ?? [])); tok = d.nextPageToken; } while (tok); return out; }, 2);
  }
  getSourceName = (repository: string) => `sources/github/${repository}`;
  normalizeSessionId = (id: string) => (id.startsWith("sessions/") ? id.slice(9) : id);

  async createSession(o: { source: string; prompt: string; title?: string | null; startingBranch?: string | null; automationMode?: string; requirePlanApproval?: boolean }): Promise<any> {
    if (!o.startingBranch) throw new Error("starting_branch is required and must be provided");
    const payload: Record<string, unknown> = { prompt: o.prompt, sourceContext: { source: o.source, githubRepoContext: { startingBranch: o.startingBranch } } };
    if (o.title) payload.title = o.title;
    const mode = o.automationMode ?? "AUTO_CREATE_PR";
    if (mode) payload.automationMode = mode;
    payload.requirePlanApproval = o.requirePlanApproval ?? true;
    const startedAt = Date.now() - 30_000;
    try { return await this.r(() => this.call("POST", "sessions", { body: payload }), 2, createRetryable); }
    catch (e) {
      if (e instanceof HttpError && e.status >= 400 && e.status < 500) {
        const recovered = await this.reconcileCreated(o.title ?? null, o.prompt, o.source, startedAt);
        if (recovered) return recovered;
      }
      throw e;
    }
  }
  getSession(id: string) { return this.r(() => this.call("GET", `sessions/${this.normalizeSessionId(id)}`)); }
  async deleteSession(id: string): Promise<boolean> { return (await this.r(() => this.call("DELETE", `sessions/${this.normalizeSessionId(id)}`, { allow404: true }))) !== null; }

  listSessions(o: { pageSize?: number; maxPages?: number; timeoutMs?: number } = {}): Promise<any[]> {
    return this.r(async () => {
      const out: any[] = []; let tok: string | undefined, pages = 0;
      for (;;) {
        const d = await this.call("GET", "sessions", { params: { pageSize: o.pageSize ?? 50, ...(tok ? { pageToken: tok } : {}) }, timeoutMs: o.timeoutMs });
        out.push(...(d.sessions ?? [])); pages++;
        tok = d.nextPageToken;
        if (!tok || (o.maxPages !== undefined && pages >= o.maxPages)) break;
      }
      return out;
    });
  }
  private async reconcileCreated(title: string | null, prompt: string, source: string | null, startedAt: number): Promise<any | null> {
    let sessions: any[];
    try { sessions = await this.listSessions({ pageSize: 100, maxPages: 3, timeoutMs: 10_000 }); } catch { return null; }
    for (const s of sessions) {
      const t = s.createTime ? Date.parse(s.createTime) : NaN;
      if (!Number.isNaN(t) && t < startedAt) continue;
      if (title && s.title !== title) continue;
      if (!title && s.prompt !== prompt) continue;
      if (source && s.sourceContext?.source !== source) continue;
      return s;
    }
    return null;
  }
  approvePlan(id: string) { return this.r(() => this.call("POST", `sessions/${this.normalizeSessionId(id)}:approvePlan`, { body: {} })); }
  sendMessage(id: string, prompt: string) { return this.r(() => this.call("POST", `sessions/${this.normalizeSessionId(id)}:sendMessage`, { body: { prompt } })); }

  /** Newest `maxActivities` activities, oldest-first; guards against repeating tokens and runaway pagination. */
  listActivities(id: string, o: { pageSize?: number; maxPages?: number; maxActivities?: number } = {}): Promise<any[]> {
    const maxPages = o.maxPages ?? MAX_PAGES(), maxAct = o.maxActivities ?? MAX_ACTIVITIES();
    return this.r(async () => {
      let recent: any[] = []; let tok: string | undefined, pages = 0; const seen = new Set<string>();
      for (;;) {
        const d = await this.call("GET", `sessions/${this.normalizeSessionId(id)}/activities`, { params: { pageSize: o.pageSize ?? 100, ...(tok ? { pageToken: tok } : {}) } });
        recent.push(...(d.activities ?? []));
        if (recent.length > maxAct) recent = recent.slice(-maxAct);
        pages++; tok = d.nextPageToken;
        if (!tok) break;
        if (seen.has(tok)) { log.warning(`Jules returned a repeating nextPageToken for session ${id} after ${pages} pages; stopping pagination.`); break; }
        if (pages >= maxPages) { log.warning(`Reached the ${maxPages}-page ceiling listing activities for session ${id}; keeping the ${recent.length} most recent.`); break; }
        seen.add(tok);
      }
      return recent;
    });
  }

  async waitForSession(id: string, maxWaitSeconds = WAIT(), pollSeconds = 30): Promise<any> {
    const t0 = Date.now();
    while (Date.now() - t0 < maxWaitSeconds * 1000) {
      const s = await this.getSession(id);
      if (s.outputs?.length || ["COMPLETED", "FAILED", "CANCELLED"].includes(s.status ?? "")) return s;
      await Bun.sleep(pollSeconds * 1000);
    }
    throw new Error(`Session ${id} did not complete within ${maxWaitSeconds} seconds`);
  }

  createPullRequestSession(o: { repository: string; prompt: string; title?: string | null; baseBranch?: string | null; requirePlanApproval?: boolean }) {
    if (!o.baseBranch) throw new Error("base_branch is required and must be provided");
    return this.createSession({ source: this.getSourceName(o.repository), prompt: o.prompt, title: o.title, startingBranch: o.baseBranch, automationMode: "AUTO_CREATE_PR", requirePlanApproval: o.requirePlanApproval });
  }
}
