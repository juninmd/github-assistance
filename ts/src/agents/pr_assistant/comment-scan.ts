/** Credentials pasted into PR comments (text outside git): one warning per exposed comment; the value is never repeated. */
import { scanText } from "../../utils/secret-scan.ts";

type R = Record<string, any>;
const WARNING_MARKER = (id: number) => `<!-- comment-secret-warning:${id} -->`;
const ID_RE = /<!-- comment-secret-warning:(\d+) -->/g;

export function findExposedComments(comments: R[]): [number, string, string[]][] {
  const out: [number, string, string[]][] = [];
  for (const c of comments) {
    const body = c.body ?? "";
    if (body.includes("comment-secret-warning")) continue; // our own warning
    const rules = [...new Set(scanText(body).map((h) => String(h.rule_id)))].sort();
    if (rules.length) out.push([Number(c.id), String(c.html_url ?? ""), rules]);
  }
  return out;
}
export const alreadyWarned = (comments: R[]) => new Set(comments.flatMap((c) => [...(c.body ?? "").matchAll(ID_RE)].map((m) => Number(m[1]))));

export function buildWarning(id: number, url: string, rules: string[]): string {
  const where = url ? `[este comentário](${url})` : `o comentário \`${id}\``;
  return [WARNING_MARKER(id), "## 🔑 Possível credencial exposta em comentário\n",
    `Detectei texto com formato de credencial em ${where} (regras: ${rules.map((r) => `\`${r}\``).join(", ")}). O valor não é repetido aqui.\n`,
    "1. **Revogue/rotacione** a credencial agora: apagar o comentário não a protege, o histórico de edições e notificações por e-mail já a expuseram.", "2. Edite ou apague o comentário."].join("\n");
}
/** Warning bodies for exposed comments that were not warned yet. */
export function pendingWarnings(comments: R[]): string[] {
  const warned = alreadyWarned(comments);
  return findExposedComments(comments).filter(([id]) => !warned.has(id)).map(([id, url, rules]) => buildWarning(id, url, rules));
}
