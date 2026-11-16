#!/usr/bin/env bun
/** Top-N repos de um usuário por commits (soma de contributors) → config/repositories.json.
 *  Uso: bun scripts/fetch-top-repos.ts --user NOME [--top 30] [--out ../config/repositories.json] [--replace] */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";

const { values: a } = parseArgs({ options: { user: { type: "string", short: "u" }, top: { type: "string", short: "n", default: "30" }, out: { type: "string", default: "../config/repositories.json" }, replace: { type: "boolean", default: false } } });
if (!a.user) { console.error("--user é obrigatório"); process.exit(2); }
const token = process.env.GITHUB_TOKEN;
const get = async (url: string) => {
  const r = await fetch(url, { headers: { "User-Agent": "github-assistant-script", ...(token ? { Authorization: `token ${token}` } : {}) } });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return { body: await r.json() as any, link: r.headers.get("link") };
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
async function contributions(url: string | null | undefined): Promise<number> {
  let next: string | null = url ? `${url}?per_page=100&anon=1` : null, total = 0;
  while (next) {
    const { body, link } = await get(next);
    if (!Array.isArray(body)) break;
    for (const c of body) total += c.contributions ?? 0;
    next = link?.match(/<([^>]+)>;\s*rel="next"/)?.[1] ?? null;
    if (next) await sleep(100);
  }
  return total;
}
console.log(`Fetching repos list for ${a.user}...`);
const { body: repos } = await get(`https://api.github.com/users/${a.user}/repos?per_page=100`);
if (!Array.isArray(repos)) { console.error("Unexpected response for repo list"); process.exit(1); }
const results: { full_name: string; commits: number }[] = [];
for (const [i, r] of repos.entries()) {
  console.log(`[${i + 1}/${repos.length}] ${r.full_name}: fetching contributors...`);
  let commits = 0;
  try { commits = await contributions(r.contributors_url); } catch (e: any) { console.log(`  failed: ${e.message}`); }
  results.push({ full_name: r.full_name, commits }); await sleep(120);
}
const top = results.sort((x, y) => y.commits - x.commits).slice(0, parseInt(a.top!, 10));
console.log("\nTop repositories by estimated commits:");
top.forEach((r, i) => console.log(`${String(i + 1).padStart(2)}. ${r.full_name} — ${r.commits} commits`));
const cfg: any = existsSync(a.out!) ? JSON.parse(readFileSync(a.out!, "utf8")) : {};
const names = top.map((r) => r.full_name);
cfg.repositories = a.replace || !cfg.repositories ? names : [...cfg.repositories, ...names.filter((n) => !cfg.repositories.includes(n))];
cfg.description ??= "List of repositories that agents are allowed to work on. Add repositories in 'owner/repo' format.";
writeFileSync(a.out!, JSON.stringify(cfg, null, 2) + "\n");
console.log(`\nUpdated ${a.out} with top ${names.length} repositories.`);
