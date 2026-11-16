/** Compact, non-blocking review rules: outdated stack/libs and README drift. */
import type { GithubClient } from "../../github/client.ts";
import { enabled } from "./review-flags.ts";

const README_MAX_CHARS = 1500;
export const STACK_RULE =
  "Stack: só se o diff tocar stack/dependências, sugira (severity info, não bloqueante) " +
  "troca de tecnologia obsoleta/depreciada ou de lib antiga por alternativa moderna, " +
  "com o motivo em uma frase (ex.: Node.js→Bun, JavaScript→TypeScript, " +
  "moment→date-fns/Temporal, requests→httpx, setup.py→pyproject.toml, " +
  "CommonJS→ESM, pacote sem manutenção→fork/substituto ativo). " +
  "Sem evidência no diff, não sugira.";
export const README_RULE =
  "README: se a mudança altera uso, comandos, configuração, variáveis de ambiente, " +
  "dependências ou comportamento documentado e o README não acompanha (ou ficou " +
  "desatualizado), aponte (severity info) o trecho a corrigir e o que escrever.";
export const RULES = `${STACK_RULE}\n${README_RULE}`;
export const advisoriesEnabled = () => enabled("REVIEW_ADVISORIES", true);
export const rulesBlock = () => (advisoriesEnabled() ? RULES : "");
export async function readmeExcerpt(gh: GithubClient, pr: any): Promise<string> {
  if (!advisoriesEnabled()) return "";
  try { return ((await gh.getReadme(pr.base.repo.full_name))?.content ?? "").slice(0, README_MAX_CHARS); } catch { return ""; }
}
export async function diffContext(gh: GithubClient, pr: any): Promise<string> {
  const rules = rulesBlock();
  if (!rules) return "";
  const ex = await readmeExcerpt(gh, pr);
  return `\n${rules}\n${ex ? `\nREADME (início):\n${ex}\n` : ""}`;
}
