/** Bot identity: when GitHub App credentials are set, every GitHub call uses the App installation token, never a PAT. */
import { GitHubAppAuth } from "../webhooks/auth.ts";

type Env = Record<string, string | undefined>;
const REFRESH_MS = 45 * 60_000;
let auth: GitHubAppAuth | null = null;
let live: string | null = null;
let timer: ReturnType<typeof setInterval> | null = null;

export const botAuthActive = () => auth !== null;
/** Latest App installation token, or null when running with a PAT. */
export const liveBotToken = () => live;

export function stopBotAuth(): void {
  if (timer) clearInterval(timer);
  timer = null; auth = null; live = null;
}

/** Returns the App token, or null when no App credentials are configured. Partial config throws (no silent PAT fallback). */
export async function initBotAuth(env: Env, appId: number | null, instId: number | null, keyPath: string | null): Promise<string | null> {
  const set = [appId, instId, keyPath].filter(Boolean).length;
  if (set === 0) return null;
  if (set < 3) throw new Error("GitHub App config incomplete: GITHUB_APP_ID, GITHUB_INSTALLATION_ID and GITHUB_APP_PRIVATE_KEY_PATH are all required");
  stopBotAuth();
  const a = new GitHubAppAuth(appId!, instId!, keyPath!);
  let t: string;
  try { t = await a.installationToken(); }
  catch (e: any) { throw new Error(`Failed to obtain GitHub App installation token: ${e?.message ?? e}`); }
  auth = a; live = t;
  env.GITHUB_TOKEN = t; // child code reads env; PAT must never win
  delete env.GH_PAT;
  timer = setInterval(() => {
    a.installationToken().then((n) => { live = n; env.GITHUB_TOKEN = n; }).catch(() => { /* keep last token; retried next tick */ });
  }, REFRESH_MS);
  timer.unref?.();
  return t;
}

/** Login the App comments as (`<slug>[bot]`); `/user` is not available to installation tokens. */
export async function botLogin(): Promise<string | null> {
  if (!auth) return null;
  const res = await fetch("https://api.github.com/app", {
    headers: { Authorization: `Bearer ${auth.jwt()}`, Accept: "application/vnd.github+json" }, signal: AbortSignal.timeout(15_000),
  });
  if (!res.ok) throw new Error(`GET /app failed (${res.status})`);
  return `${String(((await res.json()) as any).slug)}[bot]`;
}
