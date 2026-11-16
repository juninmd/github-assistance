/** Discovery and selection of free opencode models (calls the external `opencode` binary; never modifies it). */
import { randomInt } from "node:crypto";
import { run } from "../../utils/proc.ts";

export const PREFERRED_FREE_MODEL = "opencode/deepseek-v4.1-flash-free";
export const DEFAULT_FALLBACK_MODEL = "opencode/big-pickle";
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

/** env OPENCODE_MODEL > forced > preferred (attempt 0) > random other free model. */
export async function selectFreeOpencodeModel(attempt = 0): Promise<string> {
  if (process.env.OPENCODE_MODEL) return process.env.OPENCODE_MODEL;
  if (forced) return forced;
  const models = await getFreeOpencodeModels();
  const first = models[0] ?? DEFAULT_FALLBACK_MODEL;
  if (attempt === 0) return first;
  const rest = models.filter((m) => m !== first);
  return rest.length ? rest[randomInt(rest.length)] : DEFAULT_FALLBACK_MODEL;
}
