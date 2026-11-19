/** Evidence-of-change check: non-blocking `warn` when the PR body shows no proof. */
import { enabled } from "./review-flags.ts";
import { mkFinding, type Finding } from "./review-verdict.ts";

const IMAGE = /!\[[^\]]*\]\([^)]+\)|<img\s[^>]*src=|user-attachments\/assets\//i;
// "Como foi verificado"/"Verificação" is the fleet's PR template heading for test output and logs.
const SECTION = /^#{1,4}\s*(evid[eê]ncias?|evidence|screenshots?|prints?|verifica[çc][ãa]o|como foi (verificado|testado)|how (it was )?(verified|tested))(?![\p{L}\p{N}])/imu;
const MIN_SECTION_CHARS = 20;
export const EVIDENCE_SECTION = "### Evidências\n<!-- Anexe prints (antes/depois), saída de testes ou logs que provem a mudança. -->\n";
const ASK =
  "A descrição do PR não traz evidências da mudança. Adicione uma seção `Evidências` " +
  "com prints (antes/depois) ou, se não houver UI, a saída dos testes/logs que provam o resultado.";
export const evidenceRequired = () => enabled("REVIEW_REQUIRE_EVIDENCE", true);
export function hasEvidence(body?: string | null): boolean {
  const text = typeof body === "string" ? body : "";
  if (IMAGE.test(text)) return true;
  const m = SECTION.exec(text);
  if (!m) return false;
  let rest = text.slice(m.index + m[0].length).split(/^#{1,4}\s/m)[0]!;
  rest = rest.replace(/<!--[\s\S]*?-->/g, "");
  return rest.trim().length >= MIN_SECTION_CHARS;
}
export const evidenceFinding = (body?: string | null): Finding | null =>
  !evidenceRequired() || hasEvidence(body) ? null : mkFinding({ file: "(descrição do PR)", severity: "warn", issue: ASK });
