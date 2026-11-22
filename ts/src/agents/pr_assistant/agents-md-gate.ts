/** Owner rule: AGENTS.md is mandatory in every repository, so a PR on a repo without it is never merged by the bot. */
import type { GithubClient, PR } from "../../github/client.ts";

export const AGENTS_MD_MARKER = "<!-- agents-md-required -->";
const BODY = `${AGENTS_MD_MARKER}\n## 🚫 AGENTS.md ausente\n\nEste repositório não tem \`AGENTS.md\` na raiz, que é obrigatório. O bot **não aprova nem mescla** este PR até o arquivo existir (o agente \`intelligence-standardizer\` abre um PR para criá-lo).`;

/** Checks the default branch. missing = definitely absent; unknown = API error (fail closed, retried next round). */
export async function agentsMdState(gh: Pick<GithubClient, "pathExists">, repo: string): Promise<"present" | "missing" | "unknown"> {
  try { return (await gh.pathExists(repo, "AGENTS.md")) ? "present" : "missing"; }
  catch { return "unknown"; }
}
export async function noteAgentsMdMissing(gh: Pick<GithubClient, "commentOnPr">, pr: PR, comments: any[]): Promise<void> {
  if (comments.some((c) => (c.body ?? "").includes(AGENTS_MD_MARKER))) return;
  try { await gh.commentOnPr(pr, BODY); } catch { /* the block itself is already recorded */ }
}
