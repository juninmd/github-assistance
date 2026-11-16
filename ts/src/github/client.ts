/**
 * Thin GitHub REST client (fetch, no SDK). Returns raw API JSON (snake_case), so `pr.head.sha`,
 * `pr.base.repo.full_name` etc. behave exactly like the PyGithub objects the Python agents used.
 */
import { GitHubRateLimiter } from "./ratelimit.ts";
import { redactSecrets } from "../utils/secure-git.ts";
import { acceptReviewSuggestions } from "./review-suggestions.ts";

const API = "https://api.github.com";
export class GithubError extends Error {
  constructor(public status: number, message: string, public data: any = null) { super(message); }
}
export type PR = Record<string, any>;
export type Result = [boolean, string];

export class GithubClient {
  token: string;
  rateLimiter: GitHubRateLimiter | null;
  constructor(token?: string | null, rateLimiter?: GitHubRateLimiter | null, private baseUrl = API) {
    const t = token || process.env.GITHUB_TOKEN || process.env.GH_PAT;
    if (!t) throw new Error("GITHUB_TOKEN is required");
    this.token = t;
    this.rateLimiter = rateLimiter === undefined ? GitHubRateLimiter.fromEnv(t) : rateLimiter;
  }

  async request(method: string, path: string, body?: unknown, o: { raw?: boolean; accept?: string; retries?: number } = {}): Promise<any> {
    const url = path.startsWith("http") ? path : this.baseUrl + path;
    for (let attempt = 0; ; attempt++) {
      await this.rateLimiter?.acquire(url);
      let res: Response;
      try {
        res = await fetch(url, {
          method, signal: AbortSignal.timeout(300_000),
          headers: { Authorization: `token ${this.token}`, Accept: o.accept ?? "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
          body: body !== undefined ? JSON.stringify(body) : undefined,
        });
      } catch (e) { if (attempt < (o.retries ?? 3)) { await Bun.sleep(1000 * 2 ** attempt); continue; } throw e; }
      await this.rateLimiter?.observe(res.headers);
      if ([500, 502, 503].includes(res.status) && attempt < (o.retries ?? 3)) { await Bun.sleep(1000 * 2 ** attempt); continue; }
      if (!res.ok) {
        const text = await res.text();
        let data: any = null;
        try { data = JSON.parse(text); } catch { /* plain */ }
        throw new GithubError(res.status, `${res.status} ${data?.message ?? text.slice(0, 200)}`, data);
      }
      if (o.raw) return res;
      if (res.status === 204) return null;
      const text = await res.text();
      return text ? JSON.parse(text) : null;
    }
  }
  get = (p: string) => this.request("GET", p);
  post = (p: string, b?: unknown) => this.request("POST", p, b ?? {});
  patch = (p: string, b: unknown) => this.request("PATCH", p, b);
  put = (p: string, b?: unknown) => this.request("PUT", p, b ?? {});
  delete = (p: string, b?: unknown) => this.request("DELETE", p, b);

  /** Follow Link rel=next up to `limit` items. `key` unwraps envelope objects (e.g. search items). */
  async paginate<T = any>(path: string, o: { limit?: number; key?: string } = {}): Promise<T[]> {
    const out: T[] = [];
    let next: string | null = path + (path.includes("?") ? "&" : "?") + "per_page=100";
    while (next && out.length < (o.limit ?? Infinity)) {
      const res: Response = await this.request("GET", next, undefined, { raw: true });
      const data = await res.json();
      out.push(...((o.key ? data[o.key] : data) ?? []));
      next = /<([^>]+)>;\s*rel="next"/.exec(res.headers.get("link") ?? "")?.[1] ?? null;
    }
    return o.limit ? out.slice(0, o.limit) : out;
  }

  // --- reads ----------------------------------------------------------------
  searchPrs(query: string): Promise<any[]> { return this.paginate(`/search/issues?q=${encodeURIComponent(query)}`, { key: "items" }); }
  getRepo(name: string) { return this.get(`/repos/${name}`); }
  getPull(repo: string, n: number): Promise<PR> { return this.get(`/repos/${repo}/pulls/${n}`); }
  /** Resolve a search-result issue to its PR. */
  getPrFromIssue(issue: any): Promise<PR> { return this.get(issue.pull_request?.url ?? `/repos/${issue.repository_url.replace(/.*repos\//, "")}/pulls/${issue.number}`); }
  getUserRepos(o: { sort?: string; direction?: string; limit?: number | null } = {}) {
    return this.paginate(`/user/repos?sort=${o.sort ?? "updated"}&direction=${o.direction ?? "desc"}`, { limit: o.limit === undefined ? 10 : o.limit ?? undefined });
  }
  getIssueComments(repo: string, n: number) { return this.paginate(`/repos/${repo}/issues/${n}/comments`); }
  getReviewComments(repo: string, n: number) { return this.paginate(`/repos/${repo}/pulls/${n}/comments`); }
  getCommits(repo: string, n: number) { return this.paginate(`/repos/${repo}/pulls/${n}/commits`); }
  getFiles(repo: string, n: number) { return this.paginate(`/repos/${repo}/pulls/${n}/files`); }

  async getContents(repo: string, path: string, ref?: string): Promise<{ path: string; sha: string; content: string } | null> {
    try {
      const d = await this.get(`/repos/${repo}/contents/${path}${ref ? `?ref=${encodeURIComponent(ref)}` : ""}`);
      if (Array.isArray(d)) return null;
      return { path: d.path, sha: d.sha, content: Buffer.from(d.content ?? "", "base64").toString("utf8") };
    } catch (e) { if (e instanceof GithubError && e.status === 404) return null; throw e; }
  }
  async updateFile(repo: string, path: string, message: string, content: string, sha: string, branch: string) {
    return this.put(`/repos/${repo}/contents/${path}`, { message, content: Buffer.from(content, "utf8").toString("base64"), sha, branch });
  }

  // --- writes (same semantics as the Python client) -------------------------
  /** Update the PR branch against its base. Returns [ok, msg, headSha]. */
  async updatePrBranch(pr: PR, expectedHeadSha?: string): Promise<[boolean, string, string]> {
    try {
      await this.request("PUT", `/repos/${pr.base.repo.full_name}/pulls/${pr.number}/update-branch`, expectedHeadSha ? { expected_head_sha: expectedHeadSha } : {});
    } catch (e: any) {
      return [false, e instanceof GithubError ? `update-branch failed (${e.status}): ${e.message.slice(0, 200)}` : `update-branch request failed: ${e?.message ?? e}`, ""];
    }
    try { return [true, "Branch updated", (await this.getPull(pr.base.repo.full_name, pr.number)).head.sha]; }
    catch { return [true, "Branch updated (head SHA unknown)", ""]; }
  }

  /** Merge only if the head SHA still matches the SHA validated earlier. */
  async mergePr(pr: PR, mergeMethod = "squash", expectedSha?: string): Promise<Result> {
    const repo = pr.base.repo.full_name;
    let current: PR;
    try { current = await this.getPull(repo, pr.number); } catch (e: any) { return [false, `could not re-fetch PR before merge: ${e?.message ?? e}`]; }
    if (expectedSha && current.head.sha !== expectedSha)
      return [false, `HEAD changed since validation (expected ${expectedSha.slice(0, 8)}, got ${current.head.sha.slice(0, 8)}); re-validate before merging`];
    const body = { merge_method: mergeMethod, ...(expectedSha ? { sha: expectedSha } : {}) };
    try { await this.put(`/repos/${repo}/pulls/${pr.number}/merge`, body); return [true, "Merged successfully"]; }
    catch (e: any) {
      if (!GithubClient.isBaseBranchModifiedError(e)) return [false, String(e?.message ?? e)];
    }
    try {
      const fresh = await this.getPull(repo, pr.number);
      if (expectedSha && fresh.head.sha !== expectedSha) return [false, "HEAD changed after base update; re-validate before merging"];
      await this.put(`/repos/${repo}/pulls/${pr.number}/merge`, body);
      return [true, "Merged successfully after refreshing PR base"];
    } catch (e: any) { return [false, String(e?.message ?? e)]; }
  }
  static isBaseBranchModifiedError(e: unknown): boolean {
    return e instanceof GithubError && e.status === 405 && `${e.message} ${e.data?.message ?? ""}`.toLowerCase().includes("base branch was modified");
  }

  /** Last line of defence: nothing bound for a public thread may carry a credential. */
  commentOnPr(pr: PR, body: string) { return this.post(`/repos/${pr.base.repo.full_name}/issues/${pr.number}/comments`, { body: redactSecrets(body) }); }

  private async attempt(fn: () => Promise<unknown>, ok: string): Promise<Result> {
    try { await fn(); return [true, ok]; } catch (e: any) { if (e instanceof GithubError) return [false, e.message]; throw e; }
  }
  addLabelToPr(pr: PR, label: string) { return this.attempt(() => this.post(`/repos/${pr.base.repo.full_name}/issues/${pr.number}/labels`, { labels: [label] }), `Label '${label}' added`); }
  addAssigneeToPr(pr: PR, login: string) { return this.attempt(() => this.post(`/repos/${pr.base.repo.full_name}/issues/${pr.number}/assignees`, { assignees: [login] }), `Assigned '${login}'`); }
  requestReviewerOnPr(pr: PR, login: string) { return this.attempt(() => this.post(`/repos/${pr.base.repo.full_name}/pulls/${pr.number}/requested_reviewers`, { reviewers: [login] }), `Requested reviewer '${login}'`); }
  closePr(pr: PR) { return this.attempt(() => this.patch(`/repos/${pr.base.repo.full_name}/pulls/${pr.number}`, { state: "closed" }), "PR closed successfully"); }

  async prHasNonBotCommits(pr: PR, botLogin = "dependabot[bot]"): Promise<boolean> {
    try {
      const norm = (s: string) => s.trim().toLowerCase().replace(/\[bot\]$/, "");
      for (const c of await this.getCommits(pr.base.repo.full_name, pr.number)) {
        const a = c.author?.login;
        if (a && ![botLogin.toLowerCase(), norm(botLogin)].includes(a.toLowerCase())) return true;
      }
      return false;
    } catch (e) { if (e instanceof GithubError) return false; throw e; }
  }

  async commitFile(pr: PR, filePath: string, content: string, message: string): Promise<boolean> {
    try {
      const repo = pr.base.repo.full_name, f = await this.getContents(repo, filePath, pr.head.sha);
      if (!f) return false;
      await this.updateFile(repo, f.path, message, content, f.sha, pr.head.ref);
      return true;
    } catch (e) { if (e instanceof GithubError) return false; throw e; }
  }

  acceptReviewSuggestions(pr: PR, botUsernames: string[]) { return acceptReviewSuggestions(this, pr, botUsernames); }
}

// --- extra helpers used by agents -------------------------------------------------
export interface GithubClient {
  createPull(repo: string, o: { title: string; body: string; head: string; base: string; draft?: boolean }): Promise<PR>;
  createIssue(repo: string, o: { title: string; body?: string; labels?: string[] }): Promise<PR>;
}
GithubClient.prototype.createPull = function (repo, o) { return this.post(`/repos/${repo}/pulls`, o); };
GithubClient.prototype.createIssue = function (repo, o) { return this.post(`/repos/${repo}/issues`, o); };

export interface GithubClient {
  getWorkflowRuns(repo: string, o?: { status?: string; limit?: number }): Promise<any[]>;
  getBranches(repo: string): Promise<any[]>;
  compare(repo: string, base: string, head: string): Promise<any>;
  deleteBranch(repo: string, branch: string): Promise<void>;
}
GithubClient.prototype.getWorkflowRuns = async function (repo, o = {}) {
  const d = await this.get(`/repos/${repo}/actions/runs?per_page=${Math.min(o.limit ?? 30, 100)}${o.status ? `&status=${o.status}` : ""}`);
  return (d.workflow_runs ?? []).slice(0, o.limit ?? 30);
};
GithubClient.prototype.getBranches = function (repo) { return this.paginate(`/repos/${repo}/branches`); };
GithubClient.prototype.compare = function (repo, base, head) { return this.get(`/repos/${repo}/compare/${encodeURIComponent(base)}...${encodeURIComponent(head)}`); };
GithubClient.prototype.deleteBranch = async function (repo, branch) { await this.delete(`/repos/${repo}/git/refs/heads/${branch.split("/").map(encodeURIComponent).join("/")}`); };

export interface GithubClient {
  getPulls(repo: string, o?: { state?: string; sort?: string; direction?: string }): Promise<PR[]>;
  createReview(pr: PR, o: { body: string; event?: string; comments?: any[] }): Promise<any>;
  getAuthenticatedLogin(): Promise<string>;
}
GithubClient.prototype.getPulls = function (repo, o = {}) {
  return this.paginate(`/repos/${repo}/pulls?state=${o.state ?? "open"}&sort=${o.sort ?? "updated"}&direction=${o.direction ?? "desc"}`);
};
GithubClient.prototype.createReview = function (pr, o) {
  return this.post(`/repos/${pr.base.repo.full_name}/pulls/${pr.number}/reviews`, { body: o.body, event: o.event ?? "COMMENT", comments: o.comments ?? [] });
};
GithubClient.prototype.getAuthenticatedLogin = async function () { return (await this.get("/user")).login; };

export interface GithubClient { getTreePaths(repo: string, ref: string): Promise<string[]>; }
GithubClient.prototype.getTreePaths = async function (repo, ref) {
  const d = await this.get(`/repos/${repo}/git/trees/${encodeURIComponent(ref)}?recursive=1`);
  return (d.tree ?? []).map((i: any) => i.path);
};

export interface GithubClient {
  pathExists(repo: string, path: string): Promise<boolean>;
  getOpenIssues(repo: string, limit?: number): Promise<any[]>;
  getPathCommits(repo: string, path: string, limit?: number): Promise<any[]>;
}
/** True for a file or directory; false on 404 (other errors propagate). */
GithubClient.prototype.pathExists = async function (repo, path) {
  try { await this.get(`/repos/${repo}/contents/${path}`); return true; } catch (e) { if (e instanceof GithubError && e.status === 404) return false; throw e; }
};
/** Open issues excluding pull requests (the REST issues endpoint mixes them). */
GithubClient.prototype.getOpenIssues = async function (repo, limit = 50) {
  return (await this.paginate(`/repos/${repo}/issues?state=open`, { limit })).filter((i: any) => !i.pull_request).slice(0, limit);
};
GithubClient.prototype.getPathCommits = function (repo, path, limit = 1) { return this.paginate(`/repos/${repo}/commits?path=${encodeURIComponent(path)}`, { limit }); };

export interface GithubClient {
  listContents(repo: string, path?: string): Promise<any[] | null>;
  getTree(repo: string, ref: string): Promise<any[]>;
}
/** Directory listing (`path` "" = repo root); null when missing or the path is a file. */
GithubClient.prototype.listContents = async function (repo, path = "") {
  try { const d = await this.get(`/repos/${repo}/contents/${path}`); return Array.isArray(d) ? d : null; }
  catch (e) { if (e instanceof GithubError && e.status === 404) return null; throw e; }
};
/** Recursive git tree entries ({path, type, size}). */
GithubClient.prototype.getTree = async function (repo, ref) {
  return (await this.get(`/repos/${repo}/git/trees/${encodeURIComponent(ref)}?recursive=1`)).tree ?? [];
};

export interface GithubClient { getReadme(repo: string): Promise<{ path: string; content: string } | null>; }
/** Repository README (any casing/extension); null when missing. */
GithubClient.prototype.getReadme = async function (repo) {
  try { const d = await this.get(`/repos/${repo}/readme`); return { path: d.path, content: Buffer.from(d.content ?? "", "base64").toString("utf8") }; }
  catch (e) { if (e instanceof GithubError && e.status === 404) return null; throw e; }
};
