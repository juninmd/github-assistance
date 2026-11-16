/** Conventional Commits messages for every commit pushed by the agents. */
export const TYPES = ["feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"];
export const MAX_SUBJECT = 72;
const SEMANTIC = new RegExp(`^(?:${TYPES.join("|")})(?:\\([a-z0-9][a-z0-9._/-]*\\))?!?: \\S`);
export const isSemantic = (m?: string) => SEMANTIC.test((m ?? "").split("\n")[0] ?? "");
function cleanSubject(subject: string, room: number): string {
  let t = (subject ?? "").split(/\s+/).filter(Boolean).join(" ").replace(/\.+$/, "");
  t = t ? t[0].toLowerCase() + t.slice(1) : t;
  return t.slice(0, room).trimEnd() || "atualiza código";
}
export function semanticMessage(kind: string, scope: string, subject: string, body = ""): string {
  if (!TYPES.includes(kind)) kind = "chore";
  const slug = (scope ?? "").toLowerCase().replace(/[^a-z0-9._/-]+/g, "-").replace(/^-+|-+$/g, "");
  const prefix = slug ? `${kind}(${slug}): ` : `${kind}: `;
  const head = prefix + cleanSubject(subject, MAX_SUBJECT - prefix.length);
  return body.trim() ? `${head}\n\n${body.trim()}` : head;
}
