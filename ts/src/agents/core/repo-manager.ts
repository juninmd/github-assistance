/** Repository discovery and allowlist checks. */
import type { RepositoryAllowlist } from "../../config/allowlist.ts";
import type { GithubClient } from "../../github/client.ts";

type Log = (m: string, level?: string) => void;
export class RepositoryManager {
  private info = new Map<string, any | null>();
  constructor(private gh: GithubClient, private allowlist: RepositoryAllowlist, private targetOwner: string, private log: Log) {}
  static ownerOf = (r: string) => (typeof r === "string" && r.includes("/") ? r.split("/", 1)[0].trim().toLowerCase() : "");
  private isTarget = (r: string) => RepositoryManager.ownerOf(r) === this.targetOwner.trim().toLowerCase();

  async getAllowedRepositories(enforce: boolean): Promise<string[]> {
    const all = new Set(this.allowlist.listRepositories().filter((r) => this.isTarget(r)));
    const updatedAt = new Map<string, number>();
    try {
      for (const repo of await this.gh.getUserRepos({ limit: null })) {
        if (repo.owner.login.trim().toLowerCase() !== this.targetOwner.trim().toLowerCase()) continue;        if (!enforce || this.allowlist.isAllowed(repo.full_name)) {
          all.add(repo.full_name);
          const u = Date.parse(repo.updated_at ?? repo.pushed_at ?? "");
          if (!Number.isNaN(u)) updatedAt.set(repo.full_name.toLowerCase().trim(), u);
        }
      }
    } catch (e: any) { this.log(`Error fetching user repositories: ${e?.message ?? e}`, "WARNING"); }
    const keyed: [number, string][] = [];
    for (const name of all) {
      const key = name.toLowerCase().trim();
      let t = updatedAt.get(key);
      if (t === undefined) {
        try { const i = await this.getInfo(name); const u = Date.parse(i?.updated_at ?? i?.pushed_at ?? ""); if (!Number.isNaN(u)) t = u; } catch { /* epoch */ }
      }
      keyed.push([t ?? 0, key]);
    }
    const byKey = new Map([...all].map((n) => [n.toLowerCase().trim(), n]));
    return keyed.sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1])).map(([, k]) => byKey.get(k)!);
  }
  canWorkOn(repository: string, enforce: boolean) { return this.isTarget(repository) && (!enforce || this.allowlist.isAllowed(repository)); }
  async getInfo(repository: string): Promise<any | null> {
    if (this.info.has(repository)) return this.info.get(repository)!;
    if (!this.isTarget(repository)) { this.log(`Repository denied by owner scope: ${repository}`, "WARNING"); this.info.set(repository, null); return null; }
    try { const r = await this.gh.getRepo(repository); this.info.set(repository, r); return r; }
    catch (e: any) { this.log(`Error getting repository ${repository}: ${e?.message ?? e}`, "ERROR"); this.info.set(repository, null); return null; }
  }
}
