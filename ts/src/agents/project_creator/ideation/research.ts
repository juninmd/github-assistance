/** Market research for a chosen candidate: competing repos on GitHub plus web search hits. All sources fail soft. */
import type { GithubClient } from "../../../github/client.ts";

const MAX_COMPETITORS = 5, README_CHARS = 1800, DDG_URL = "https://html.duckduckgo.com/html/";
const DDG_RESULT = /class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]*?class="result__snippet"[^>]*>([\s\S]*?)<\/a>/g;
const unescapeHtml = (s: string) => s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#x27;|&#39;/g, "'");
const clean = (s: string) => unescapeHtml(s.replace(/<[^>]+>/g, "")).trim();
type Log = (m: string, level?: string) => void;
export type Research = { competitors: Record<string, any>[]; web: Record<string, any>[] };
export type HttpGet = (url: string, o: { headers: Record<string, string>; signal: AbortSignal }) => Promise<{ ok: boolean; status: number; text(): Promise<string> }>;

export class MarketResearcher {
  constructor(private gh: Pick<GithubClient, "get" | "getReadme" | "listContents">, private log: Log, private httpGet: HttpGet = fetch as any) {}

  async research(queries: unknown[], owner: string): Promise<Research> {
    const qs = queries.filter((q): q is string => typeof q === "string" && !!q.trim()).slice(0, 3);
    return { competitors: await this.githubCompetitors(qs, owner.toLowerCase()), web: await this.web(qs) };
  }

  private async githubCompetitors(queries: string[], owner: string) {
    const found = new Map<string, any>();
    for (const q of queries) {
      try {
        const sq = encodeURIComponent(`${q} in:name,description,readme fork:false`);
        const d = await this.gh.get(`/search/repositories?q=${sq}&sort=stars&order=desc&per_page=${MAX_COMPETITORS}`);
        for (const r of (d.items ?? []).slice(0, MAX_COMPETITORS)) if (r.full_name.split("/")[0].toLowerCase() !== owner && !found.has(r.full_name)) found.set(r.full_name, r);
      } catch (e: any) { this.log(`GitHub competitor search failed for '${q}': ${e?.message ?? e}`, "WARNING"); }
    }
    const ranked = [...found.values()].sort((a, b) => (b.stargazers_count ?? 0) - (a.stargazers_count ?? 0)).slice(0, MAX_COMPETITORS);
    return Promise.all(ranked.map((r) => this.summarize(r)));
  }

  private async summarize(r: any) {
    let readme = "", files: string[] = [];
    try { readme = ((await this.gh.getReadme(r.full_name))?.content ?? "").slice(0, README_CHARS); } catch (e: any) { this.log(`No README for ${r.full_name}: ${e?.message ?? e}`, "DEBUG"); }
    try { files = ((await this.gh.listContents(r.full_name, "")) ?? []).map((c) => c.path).slice(0, 25); } catch (e: any) { this.log(`No file listing for ${r.full_name}: ${e?.message ?? e}`, "DEBUG"); }
    return { name: r.full_name, url: r.html_url, stars: r.stargazers_count ?? 0, language: r.language ?? null, description: r.description ?? "", root_files: files, readme_excerpt: readme };
  }

  private async web(queries: string[]) {
    const out: Record<string, any>[] = [];
    for (const q of queries.slice(0, 2)) {
      try {
        const res = await this.httpGet(`${DDG_URL}?q=${encodeURIComponent(q)}`, { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(15_000) });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.text();
        for (const m of [...body.matchAll(DDG_RESULT)].slice(0, 5)) out.push({ title: clean(m[2]), url: unescapeHtml(m[1]), snippet: clean(m[3]) });
      } catch (e: any) { this.log(`Web search failed for '${q}': ${e?.message ?? e}`, "WARNING"); }
    }
    return out.slice(0, 8);
  }
}

/** Compact text block for prompts. */
export function formatResearch(r: Partial<Research>): string {
  const lines: string[] = [];
  for (const c of r.competitors ?? []) lines.push(`- ${c.name} (${c.stars}★, ${c.language || "n/a"}) ${c.url}\n  ${c.description}\n  files: ${c.root_files.slice(0, 15).join(", ")}\n  README: ${c.readme_excerpt.slice(0, 900).replace(/\n/g, " ")}`);
  for (const w of r.web ?? []) lines.push(`- [web] ${w.title} ${w.url} — ${w.snippet}`);
  return lines.join("\n") || "none found";
}
