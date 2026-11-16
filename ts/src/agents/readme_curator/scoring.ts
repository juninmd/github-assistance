/** Rubric-based README quality scoring: 0-100 score plus the list of missing elements (pure). */
export const DEFAULT_MIN_SCORE = 80;
const BADGE = /(shields\.io|badge\.svg|img\.shields|badgen\.net)/i, IMAGE = /(!\[[^\]]*\]\(|```mermaid|<img\s)/i, HEADER = /^#{2,3}\s+\S/gm;
const INSTALL = ["install", "instala", "setup", "getting started", "começando", "pré-requisit", "prerequisit"];
const USAGE = ["usage", "uso", "quickstart", "como usar", "example", "exemplo", "run", "execut"];
const CONFIG = ["config", "environment variable", "variável de ambiente", "variáveis de ambiente", ".env", "options"];
const LICENSE = ["license", "licença", "licencia"], CONTRIB = ["contributing", "contribui", "development", "desenvolvimento"];

/** The prose right after the title, skipping badges/images and headers. */
function firstParagraph(body: string): string {
  const p: string[] = [];
  for (const line of body.split(/\r?\n/)) {
    const s = line.trim();
    if (!s) { if (p.length) break; continue; }
    if (["#", "![", "[![", "<img", "|", ">", "-", "*"].some((x) => s.startsWith(x))) { if (p.length) break; continue; }
    p.push(s);
  }
  return p.join(" ");
}
export type ReadmeScore = { score: number; missing: string[] };
export const needsWork = (s: ReadmeScore, min: number) => s.score < min;
const has = (c: string, needles: string[]) => { const l = c.toLowerCase(); return needles.some((n) => l.includes(n)); };

export function scoreReadme(content?: string | null): ReadmeScore {
  const text = content ?? "";
  if (!text.trim()) return { score: 0, missing: ["title", "description", "installation", "usage"] };
  let score = 0; const missing: string[] = [];
  const check = (label: string, pts: number, ok: boolean) => { if (ok) score += pts; else missing.push(label); };
  const stripped = text.trimStart(), nl = stripped.indexOf("\n"), body = nl >= 0 ? stripped.slice(nl + 1) : "";
  check("title", 5, stripped.startsWith("# "));
  check("description", 10, firstParagraph(body).length >= 120);
  check("sections", 15, (text.match(HEADER) ?? []).length >= 4);
  check("installation", 15, has(text, INSTALL)); check("usage", 15, has(text, USAGE)); check("configuration", 10, has(text, CONFIG));
  check("badges", 10, BADGE.test(text)); check("license", 5, has(text, LICENSE)); check("contributing", 5, has(text, CONTRIB));
  check("visual (diagram/screenshot)", 10, IMAGE.test(text));
  return { score: Math.min(score, 100), missing };
}
