/** Credential-safe git plumbing: token-free URLs, per-command auth header, env scrubbing, redaction. */
export const GITHUB_HOST = "github.com";
export const DEFAULT_ENV_DENY = ["ADMIN_API_TOKEN", "GEMINI_API_KEY", "GH_PAT", "GITHUB_TOKEN", "GITHUB_APP_PRIVATE_KEY", "GITHUB_WEBHOOK_SECRET", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"];
export const DEFAULT_ENV_KEEP = ["LITELLM_API_KEY"];
export const WILDCARD = /(_KEY|_TOKEN|_SECRET|_PAT)$/;

const envList = (name: string) => (process.env[name] ?? "").split(",").map((s) => s.trim()).filter(Boolean);
export const githubCloneUrl = (repository: string) => `https://${GITHUB_HOST}/${repository}.git`;

/** `git -c` args that authenticate a single command; token never touches disk. */
export function authConfigArgs(token?: string | null): string[] {
  const t = token || process.env.GITHUB_TOKEN || process.env.GH_PAT || "";
  if (!t) return [];
  const header = `Authorization: Basic ${Buffer.from(`x-access-token:${t}`).toString("base64")}`;
  return ["-c", `http.https://${GITHUB_HOST}/.extraheader=${header}`];
}

const REDACTIONS: [RegExp, string][] = [
  [/x-access-token:[^@\s]+@/g, "x-access-token:REDACTED@"],
  [/(Authorization:\s*(?:Basic|Bearer|token)\s+)\S+/gi, "$1REDACTED"],
  [/(extraheader=)\S+(?:\s+\S+)?/gi, "$1REDACTED"],
  [/\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})/g, "REDACTED"],
  [/\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})/g, "REDACTED"],
  [/\b\d{8,10}:[A-Za-z0-9_-]{35}\b/g, "REDACTED"],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)/g, "REDACTED"],
  [/\b((?:api[_-]?key|token|secret|password|passwd)\s*[=:]\s*)["']?[^\s"',;]{8,}/gi, "$1REDACTED"],
];
export function redactSecrets(text?: string | null): string {
  let out = text ?? "";
  for (const [re, rep] of REDACTIONS) out = out.replace(re, rep);
  return out;
}
export const redactCmd = (cmd?: unknown[]) => (cmd?.length ? redactSecrets(cmd.map(String).join(" ")) : "");

/** Copy of env without credentials (deny-list + *_KEY/_TOKEN/_SECRET/_PAT; keep-list wins). */
export function scrubEnv(env: Record<string, string | undefined> = process.env, o: { extraDeny?: string[]; extraKeep?: string[] } = {}): Record<string, string> {
  const deny = new Set([...DEFAULT_ENV_DENY, ...envList("OPENCODE_ENV_DENY"), ...(o.extraDeny ?? [])]);
  const keep = new Set([...DEFAULT_ENV_KEEP, ...envList("OPENCODE_ENV_KEEP"), ...(o.extraKeep ?? [])]);
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(env)) {
    if (v === undefined) continue;
    if (keep.has(k) || !(deny.has(k) || WILDCARD.test(k))) out[k] = v;
  }
  return out;
}
