/** Owner veto and slash commands read from PR comments: `/hold`, `/unhold`, `/merge`, `/review` (newest wins). */
const COMMAND_RE = /^\s*\/(hold|unhold|merge|review)\b/i;
type C = Record<string, any>;
export type OwnerCommands = { hold: boolean; mergeAt: number | null; reviewAt: number | null };

/** Bot output always carries an HTML marker or the origin footer; a human comment does not. */
export const isBotGenerated = (body: string) => body.includes("<!--") || body.includes("Origem Automatizada");
/** A comment the owner wrote by hand (not the bot, even when the bot ran with the owner's PAT). */
export function isOwnerHuman(c: C, owner: string): boolean {
  const login = String(c.user?.login ?? "").toLowerCase();
  return login === owner.toLowerCase() && c.user?.type !== "Bot" && !!c.body && !isBotGenerated(String(c.body));
}
export const isCommand = (body: string) => COMMAND_RE.test(body);
const time = (c: C) => { const t = Date.parse(c.created_at ?? ""); return Number.isNaN(t) ? 0 : t; };

export function ownerCommands(comments: C[], owner: string): OwnerCommands {
  const out: OwnerCommands = { hold: false, mergeAt: null, reviewAt: null };
  for (const c of [...comments].sort((a, b) => time(a) - time(b))) {
    if (!isOwnerHuman(c, owner)) continue;
    const m = COMMAND_RE.exec(String(c.body));
    if (!m) continue;
    const cmd = m[1]!.toLowerCase();
    if (cmd === "hold") out.hold = true;
    else if (cmd === "unhold") out.hold = false;
    else if (cmd === "merge") out.mergeAt = time(c);
    else out.reviewAt = time(c);
  }
  return out;
}
/** `/merge` counts only when written after the newest commit of the PR (a later push needs a new `/merge`). */
export const mergeCommandValid = (cmds: OwnerCommands, headCommitAt: number | null) =>
  cmds.mergeAt !== null && headCommitAt !== null && cmds.mergeAt >= headCommitAt;
/** Committer date of the PR's newest commit, or null when unknown. */
export async function headCommitAt(gh: { getCommits(repo: string, n: number): Promise<C[]> }, pr: C): Promise<number | null> {
  try {
    const commits = await gh.getCommits(pr.base.repo.full_name, pr.number);
    const head = commits.find((c) => c.sha === pr.head.sha) ?? commits[commits.length - 1];
    const t = Date.parse(head?.commit?.committer?.date ?? "");
    return Number.isNaN(t) ? null : t;
  } catch { return null; }
}
