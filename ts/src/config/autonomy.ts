/** Per-repository autonomy policy: observe/suggest/fix/merge (config/autonomy.json). */
import { readFileSync } from "node:fs";

export const MODES = ["observe", "suggest", "fix", "merge"] as const;
export type RepoAutonomy = {
  mode: string; max_attempts: number; require_evidence: boolean;
  required_checks: string[]; allowed_paths: string[]; merge: boolean;
};
const normMode = (v: any) => { const m = String(v || "observe").trim().toLowerCase(); return (MODES as readonly string[]).includes(m) ? m : "observe"; };
const normList = (v: any): string[] => (Array.isArray(v) ? v.map(String).filter((s) => s.trim()) : []);
const num = (v: any, d: number) => Number(v) || d;

export const allowsMerge = (p: RepoAutonomy) => p.merge && p.mode === "merge";
export const allowsWrite = (p: RepoAutonomy) => p.mode === "fix" || p.mode === "merge";

export class AutonomyPolicy {
  private repos = new Map<string, RepoAutonomy>();
  private def: RepoAutonomy = { mode: "observe", max_attempts: 3, require_evidence: true, required_checks: [], allowed_paths: [], merge: false };
  constructor(public path = "config/autonomy.json") { this.load(); }

  load(): void {
    let d: any = {};
    try { d = JSON.parse(readFileSync(this.path, "utf8")); } catch { /* defaults */ }
    const df = d.defaults ?? {};
    this.def = {
      mode: normMode(df.mode), max_attempts: num(df.max_attempts, 3), require_evidence: df.require_evidence ?? true,
      required_checks: normList(df.required_checks), allowed_paths: normList(df.allowed_paths), merge: !!df.merge,
    };
    for (const [repo, c] of Object.entries<any>(d.repositories ?? {})) {
      this.repos.set(repo.toLowerCase().trim(), {
        mode: normMode(c.mode ?? this.def.mode), max_attempts: num(c.max_attempts ?? this.def.max_attempts, 3),
        require_evidence: c.require_evidence ?? this.def.require_evidence,
        required_checks: normList(c.required_checks?.length ? c.required_checks : this.def.required_checks),
        allowed_paths: normList(c.allowed_paths?.length ? c.allowed_paths : this.def.allowed_paths),
        merge: c.merge ?? this.def.merge,
      });
    }
  }
  forRepository(repo: string): RepoAutonomy { return this.repos.get(String(repo).toLowerCase().trim()) ?? this.def; }
  allowMerge(repo: string) { return allowsMerge(this.forRepository(repo)); }
  toDict() {
    return { defaults: this.def, repositories: Object.fromEntries([...this.repos].sort(([a], [b]) => a.localeCompare(b))) };
  }
}
