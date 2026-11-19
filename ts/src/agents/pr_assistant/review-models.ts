/** Candidate opencode models for the advisory review: free first, cloud/auto last. */
import { run } from "../../utils/proc.ts";
import { DEFAULT_CLOUD_MODEL, DEFAULT_FALLBACK_MODEL, PREFERRED_FREE_MODEL, cloudModel } from "../opencode/models.ts";

export { DEFAULT_CLOUD_MODEL, cloudModel };
const DEFAULT_MAX_FREE = 3;
let cache: string[] | null = null;
export const resetModelCache = () => { cache = null; };

const maxFree = () => { const n = parseInt(process.env.OPENCODE_REVIEW_MAX_FREE_MODELS || "", 10); return Number.isNaN(n) ? DEFAULT_MAX_FREE : Math.max(0, n); };
const shuffle = <T>(xs: T[]) => { const a = [...xs]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

/** Free opencode models, cheapest first; cached for the process lifetime. */
export async function freeOpencodeModels(): Promise<string[]> {
  if (cache === null) {
    let free: string[] = [];
    try {
      const r = await run(["opencode", "models"], { timeoutMs: 25_000 });
      free = (r.stdout || "").split(/\r?\n/).map((m) => m.trim()).filter((m) => m && (m.endsWith("-free") || m === DEFAULT_FALLBACK_MODEL));
    } catch { free = []; }
    cache = free.length && free.includes(PREFERRED_FREE_MODEL) ? [PREFERRED_FREE_MODEL, ...shuffle(free.filter((m) => m !== PREFERRED_FREE_MODEL))] : free.length ? free : [DEFAULT_FALLBACK_MODEL];
  }
  return [...cache];
}
// The free tier is an ACCOUNT-wide quota: one FreeUsageLimitError means every `-free` model will refuse until it resets.
const FREE_QUOTA_RE = /FreeUsageLimitError|Free usage limit reached/i;
const FREE_QUOTA_BACKOFF_MS = 60 * 60_000;
let freeExhaustedUntil = 0;
export const isFreeModel = (m: string) => m.endsWith("-free");
export const isFreeQuotaError = (text?: string | null) => !!text && FREE_QUOTA_RE.test(text);
export const markFreeExhausted = (now = Date.now()) => { freeExhaustedUntil = now + FREE_QUOTA_BACKOFF_MS; };
export const freeExhausted = (now = Date.now()) => now < freeExhaustedUntil;
export const resetFreeQuota = () => { freeExhaustedUntil = 0; };

/** Free opencode models (bounded) followed by the cloud/auto fallback; cloud only while the free quota is exhausted. */
export async function candidateModels(): Promise<string[]> {
  const models = freeExhausted() ? [] : (await freeOpencodeModels()).slice(0, maxFree()), cloud = cloudModel();
  if (!models.includes(cloud)) models.push(cloud);
  return models;
}
