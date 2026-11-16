/** Deterministic part of conflict resolution: what kind of conflict each file has, what must never reach a model, and what would fail at push. */
import { basename } from "node:path";
import { run } from "../../utils/proc.ts";
import type { HunkContext } from "./conflict-hunks.ts";

/** Lockfiles are regenerated from the merged manifest, never merged by hand or by a model. */
export const LOCKFILE_COMMANDS: Record<string, string[]> = {
  "pnpm-lock.yaml": ["pnpm", "install", "--lockfile-only", "--ignore-scripts"],
  "yarn.lock": ["yarn", "install", "--mode", "update-lockfile"],
  "package-lock.json": ["npm", "install", "--package-lock-only", "--ignore-scripts"],
  "bun.lock": ["bun", "install", "--lockfile-only", "--ignore-scripts"],
};
const OTHER_LOCKFILES = new Set(["cargo.lock", "poetry.lock", "uv.lock", "pipfile.lock", "composer.lock", "gemfile.lock", "go.sum", "pubspec.lock",
  "packages.lock.json", "flake.lock", "podfile.lock", "bun.lockb", "npm-shrinkwrap.json"]);
export const canRegenerate = (path: string) => basename(path) in LOCKFILE_COMMANDS;
export const isLockfile = (path: string) => canRegenerate(path) || OTHER_LOCKFILES.has(basename(path).toLowerCase());

export type ConflictKinds = { content: string[]; structural: string[] };
/** `content`: both sides edited the file (markers inside). `structural`: one side deleted, renamed or added it — a decision, not a merge. */
export async function conflictKinds(dir: string): Promise<ConflictKinds> {
  const out: ConflictKinds = { content: [], structural: [] };
  const r = await run(["git", "status", "--porcelain", "-z"], { cwd: dir, timeoutMs: 30_000 });
  for (const entry of r.stdout.split("\0")) {
    const xy = entry.slice(0, 2), file = entry.slice(3);
    if (!file) continue;
    if (xy === "UU" || xy === "AA") out.content.push(file);
    else if (["DU", "UD", "AU", "UA", "DD"].includes(xy)) out.structural.push(file);
  }
  return out;
}
/** Scopes of a classic token (`x-oauth-scopes`); null when unknown (app or fine-grained token, no network). */
export async function tokenScopes(token = process.env.GITHUB_TOKEN || process.env.GH_PAT || ""): Promise<string[] | null> {
  if (!token) return null;
  try {
    const res = await fetch("https://api.github.com/user", { headers: { authorization: `Bearer ${token}`, "user-agent": "git-automation" }, signal: AbortSignal.timeout(10_000) });
    const header = res.headers.get("x-oauth-scopes");
    return header === null ? null : header.split(",").map((s) => s.trim()).filter(Boolean);
  } catch { return null; }
}
/**
 * GitHub rejects a push whose merge commit differs from either parent in `.github/workflows` unless the token has the
 * `workflow` scope. Knowing that before any model call turns an opaque push failure into a clear, cheap answer.
 */
export async function workflowPushBlocked(dir: string, baseBranch: string, scopes: () => Promise<string[] | null> = tokenScopes): Promise<string> {
  const d = await run(["git", "diff", "--name-only", "HEAD", `upstream/${baseBranch}`, "--", ".github/workflows"], { cwd: dir, timeoutMs: 30_000 });
  const files = d.stdout.split(/\r?\n/).map((f) => f.trim()).filter(Boolean);
  if (d.code !== 0 || !files.length) return "";
  const have = await scopes();
  if (have === null || have.includes("workflow")) return "";
  return `O token não tem o escopo \`workflow\` e este merge envolve ${files.slice(0, 3).map((f) => `\`${f}\``).join(", ")}; o GitHub recusaria o push. ` +
    "Adicione o escopo `workflow` ao token ou atualize o branch manualmente.";
}
export type ConflictInfo = { file: string; title: string; head: string; base: string };
/** One block, both sides named, the common ancestor shown: the model merges intents instead of guessing which side is "newer". */
export function conflictPrompt(info: ConflictInfo, c: HunkContext): string {
  const side = (ls: string[]) => ls.join("") || "(vazio: este lado removeu o trecho)\n";
  return `You are resolving ONE git merge conflict in \`${info.file}\`.\n` +
    `Pull request: "${info.title}". Its branch \`${info.head}\` is being updated with the target branch \`${info.base}\`.\n` +
    "Work out what each side changed relative to BASE and write code that keeps BOTH intents. " +
    "If one side deleted code that the other edited, keep the edit unless deleting it is clearly the point of the change. " +
    "Never invent behaviour that neither side has, and do not reformat.\n\n" +
    `--- OURS (the pull request, \`${info.head}\`)\n${side(c.hunk.ours)}` +
    (c.hunk.base ? `--- BASE (common ancestor, what both sides started from)\n${side(c.hunk.base)}` : "") +
    `--- THEIRS (the target branch, \`${info.base}\`)\n${side(c.hunk.theirs)}` +
    `--- Code right before the conflict (read-only, do NOT repeat it)\n${c.pre.join("") || "(início do arquivo)\n"}` +
    `--- Code right after the conflict (read-only, do NOT repeat it)\n${c.post.join("") || "(fim do arquivo)\n"}\n` +
    "Reply with ONLY the lines that replace the conflict: no markers, no surrounding context, no markdown fences, no commentary. " +
    "If the two intents cannot be merged safely, reply exactly: CANNOT_RESOLVE";
}
