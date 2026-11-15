/** Repository allowlist: which repos/owners agents may touch (config/repositories.json). */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { getLogger } from "../utils/logger.ts";

const log = getLogger("allowlist");
const norm = (v: unknown) => (typeof v === "string" ? v.toLowerCase().trim() : "");
const toSet = (xs: unknown) => new Set((Array.isArray(xs) ? xs : []).map(norm).filter(Boolean));

export class RepositoryAllowlist {
  private repos = new Set<string>(); private users = new Set<string>();
  constructor(public path = process.env.REPOSITORY_ALLOWLIST_PATH ?? "config/repositories.json") { this.load(); }

  load(): void {
    try {
      if (!existsSync(this.path)) { log.warning(`Allowlist file not found at ${this.path}. Using empty allowlist.`); this.repos = new Set(); this.users = new Set(); return; }
      const d = JSON.parse(readFileSync(this.path, "utf8"));
      this.repos = toSet(d.repositories); this.users = toSet(d.users);
      log.info(`Loaded ${this.repos.size} repositories and ${this.users.size} users from allowlist`);
    } catch (e: any) { log.error(`Error loading allowlist: ${e?.message ?? e}`); this.repos = new Set(); this.users = new Set(); }
  }
  save(): void {
    try {
      mkdirSync(dirname(this.path), { recursive: true });
      writeFileSync(this.path, JSON.stringify({
        repositories: [...this.repos].sort(), users: [...this.users].sort(),
        description: "List of repositories and users that agents are allowed to work on",
      }, null, 2));
    } catch (e: any) { log.error(`Error saving allowlist: ${e?.message ?? e}`); }
  }
  isAllowed(repository: string): boolean {
    const n = norm(repository);
    if (!n) return false;
    if (this.repos.has(n)) return true;
    return n.includes("/") && this.users.has(n.split("/")[0]);
  }
  isUserAllowed(u: string) { return this.users.has(norm(u)); }
  private mutate(set: Set<string>, v: string, add: boolean): boolean {
    const n = norm(v);
    if (!n || set.has(n) === add) return false;
    add ? set.add(n) : set.delete(n);
    this.save();
    return true;
  }
  addUser(u: string) { return this.mutate(this.users, u, true); }
  removeUser(u: string) { return this.mutate(this.users, u, false); }
  addRepository(r: string) { return this.mutate(this.repos, r, true); }
  removeRepository(r: string) { return this.mutate(this.repos, r, false); }
  listUsers() { return [...this.users].sort(); }
  listRepositories() { return [...this.repos].sort(); }
  clear() { this.repos.clear(); this.save(); }
}
