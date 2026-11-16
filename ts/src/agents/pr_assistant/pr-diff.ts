/** Shared PR diff collection and review prompt, bounded for a single LLM/opencode call. */
import type { GithubClient, PR } from "../../github/client.ts";
import { diffContext } from "./review-advisories.ts";

const MAX_DIFF_CHARS = 12000, MAX_FILES = 30;
export async function collectDiff(gh: GithubClient, pr: PR): Promise<string> {
  const parts: string[] = []; let total = 0;
  for (const f of (await gh.getFiles(pr.base.repo.full_name, pr.number)).slice(0, MAX_FILES)) {
    if (!f.patch) continue;
    const chunk = `--- ${f.filename} ---\n${f.patch}\n`;
    if (total + chunk.length > MAX_DIFF_CHARS) { parts.push(`--- ${f.filename} --- (truncated)`); break; }
    parts.push(chunk); total += chunk.length;
  }
  return parts.join("\n");
}
export async function buildReviewPrompt(gh: GithubClient, pr: PR, diff: string): Promise<string> {
  return "You are a senior software engineer doing a pull request code review.\n" +
    "Review ONLY the diff below for real defects: bugs, security issues " +
    "(injection, secrets, unsafe input handling), and correctness regressions.\n" +
    "Ignore style nits. Be concise. If there is nothing to flag, reply exactly: " +
    "No issues found.\n" +
    "Format findings as a short markdown bullet list, each bullet naming the " +
    "file and the concrete problem.\n\n" +
    `PR title: ${pr.title}\n${await diffContext(gh, pr)}\nDiff:\n${diff}`;
}
