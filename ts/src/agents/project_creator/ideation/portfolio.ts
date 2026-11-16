/** Owner portfolio profile: what the owner builds by hand vs. what earlier runs auto-generated. */
export const AUTONOMOUS_MARKER = "criado de forma autônoma";
const MAX_EXEMPLARS = 25, MAX_GENERATED = 15, MAX_LANGUAGES = 4, MIN_DESCRIPTION = 15;
const NON_STACK = new Set(["dockerfile", "makefile", "shell", "html", "css", "powershell", "batchfile"]);
export type Portfolio = { exemplars: string[]; generated: string[]; languages: string[] };
const text = (v: unknown) => (typeof v === "string" ? v.trim() : "");

/** Split the owner's repos into hand-built exemplars and auto-generated ones (the anti-pattern). */
export function buildPortfolio(repos: Record<string, any>[], owner = ""): Portfolio {
  const exemplars: string[] = [], generated: string[] = [], langs = new Map<string, number>();
  for (const r of repos) {
    const name = text(r.name);
    if (!name || r.archived === true || r.fork === true) continue;
    const login = text(r.owner?.login);
    if (owner && login && login.toLowerCase() !== owner.toLowerCase()) continue; // collaborator/org repos don't define the owner's taste
    const description = text(r.description).split(/\s+/).filter(Boolean).join(" ");
    if (description.toLowerCase().includes(AUTONOMOUS_MARKER)) { generated.push(name); continue; }
    const language = text(r.language);
    if (language && !NON_STACK.has(language.toLowerCase())) langs.set(language, (langs.get(language) ?? 0) + 1);
    if (description.length >= MIN_DESCRIPTION && exemplars.length < MAX_EXEMPLARS) exemplars.push(`${name} (${language || "n/a"}): ${description.slice(0, 120)}`);
  }
  const languages = [...langs.entries()].sort((a, b) => b[1] - a[1]).slice(0, MAX_LANGUAGES).map(([l]) => l); // stable: first seen wins ties
  return { exemplars, generated: generated.slice(0, MAX_GENERATED), languages };
}
