/** Owner veto and slash commands read from PR comments: `/hold`, `/unhold`, `/merge`, `/review` (newest wins). */
const COMMAND_RE = /^\s*\/(hold|unhold|merge|review)\b(?:[ \t]+([0-9a-f]{7,40})\b)?/i;
// Comments the bot posts without an HTML marker (it may post as the owner when running on the owner's PAT).
const BOT_PHRASES = ["Origem Automatizada", "**Nao foi possivel resolver os conflitos", "**Conflitos de merge resolvidos", "**Tentativa "];
type C = Record<string, any>;
export type OwnerCommands = { hold: boolean; mergeAt: number | null; mergeSha: string | null; reviewAt: number | null };

/** Bot output always carries an HTML marker or the origin footer; a human comment does not. */
export const isBotGenerated = (body: string) => body.includes("<!--") || body.trim().startsWith("@dependabot") || BOT_PHRASES.some((p) => body.includes(p));
/** A comment the owner wrote by hand (not the bot, even when the bot ran with the owner's PAT). */
export function isOwnerHuman(c: C, owner: string): boolean {
  const login = String(c.user?.login ?? "").toLowerCase();
  return login === owner.toLowerCase() && c.user?.type !== "Bot" && !!c.body && !isBotGenerated(String(c.body));
}
export const isCommand = (body: string) => COMMAND_RE.test(body);
const time = (c: C) => { const t = Date.parse(c.created_at ?? ""); return Number.isNaN(t) ? 0 : t; };

export function ownerCommands(comments: C[], owner: string): OwnerCommands {
  const out: OwnerCommands = { hold: false, mergeAt: null, mergeSha: null, reviewAt: null };
  for (const c of [...comments].sort((a, b) => time(a) - time(b))) {
    if (!isOwnerHuman(c, owner)) continue;
    const m = COMMAND_RE.exec(String(c.body));
    if (!m) continue;
    const cmd = m[1]!.toLowerCase();
    if (cmd === "hold") out.hold = true;
    else if (cmd === "unhold") out.hold = false;
    else if (cmd === "merge") { out.mergeAt = time(c); out.mergeSha = m[2]?.toLowerCase() ?? null; }
    else out.reviewAt = time(c);
  }
  return out;
}
/**
 * `/merge <sha>` pins the approval to that head; bare `/merge` counts only when written after the newest commit's
 * committer date (weaker: that date is set by whoever pushes). Any later push needs a new `/merge`.
 */
export function mergeCommandValid(cmds: OwnerCommands, headCommitAt: number | null, headSha = ""): boolean {
  if (cmds.mergeAt === null) return false;
  if (cmds.mergeSha) return headSha.toLowerCase().startsWith(cmds.mergeSha);
  return headCommitAt !== null && cmds.mergeAt >= headCommitAt;
}
/** Committer date of the PR's newest commit, or null when unknown. */
export async function headCommitAt(gh: { getCommits(repo: string, n: number): Promise<C[]> }, pr: C): Promise<number | null> {
  try {
    const commits = await gh.getCommits(pr.base.repo.full_name, pr.number);
    const head = commits.find((c) => c.sha === pr.head.sha) ?? commits[commits.length - 1];
    const t = Date.parse(head?.commit?.committer?.date ?? "");
    return Number.isNaN(t) ? null : t;
  } catch { return null; }
}
