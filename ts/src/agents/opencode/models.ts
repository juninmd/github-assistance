/** Discovery and selection of free opencode models (calls the external `opencode` binary; never modifies it). */
import { randomInt } from "node:crypto";
import { run } from "../../utils/proc.ts";

export const PREFERRED_FREE_MODEL = "opencode/deepseek-v4.1-flash-free";
export const DEFAULT_FALLBACK_MODEL = "opencode/big-pickle";
/** Default cloud model (cluster LiteLLM): used only after a free model fails. */
export const DEFAULT_CLOUD_MODEL = "litellm/cloud/auto";
export const cloudModel = () => process.env.OPENCODE_REVIEW_MODEL || DEFAULT_CLOUD_MODEL;
let modelsCache: string[] | null = null;
let forced: string | null = null;

export const setForcedModel = (m: string | null) => { forced = m; };
export const resetModelsCache = () => { modelsCache = null; forced = null; };
const shuffle = <T>(xs: T[]) => { const a = [...xs]; for (let i = a.length - 1; i > 0; i--) { const j = randomInt(i + 1); [a[i], a[j]] = [a[j], a[i]]; } return a; };

export async function getFreeOpencodeModels(timeoutSeconds = 20): Promise<string[]> {
  if (modelsCache === null) {
    const r = await run([Bun.which("opencode") ?? "opencode", "models"], { timeoutMs: timeoutSeconds * 1000 });
    if (r.code === 0 && r.stdout) {
      const free = r.stdout.split("\n").map((m) => m.trim()).filter((m) => m && (m.endsWith("-free") || m === DEFAULT_FALLBACK_MODEL));
      modelsCache = free.length ? free : [DEFAULT_FALLBACK_MODEL];
    } else modelsCache = [DEFAULT_FALLBACK_MODEL];
  }
  const models = [...modelsCache];
  if (models.includes(PREFERRED_FREE_MODEL)) return [PREFERRED_FREE_MODEL, ...shuffle(models.filter((m) => m !== PREFERRED_FREE_MODEL))];
  return shuffle(models);
}

/** env OPENCODE_MODEL > forced > preferred free (attempt 0) > cloud/auto after an error (attempt > 0). */
export async function selectFreeOpencodeModel(attempt = 0): Promise<string> {
  if (process.env.OPENCODE_MODEL) return process.env.OPENCODE_MODEL;
  if (forced) return forced;
  if (attempt > 0) return cloudModel();
  const models = await getFreeOpencodeModels();
  return models[0] ?? DEFAULT_FALLBACK_MODEL;
}
