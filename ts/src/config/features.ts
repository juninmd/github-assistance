/** Optional TOML feature file layered under env: env/.env > config/features.toml > defaults. */
import { existsSync, readFileSync } from "node:fs";
import { getLogger } from "../utils/logger.ts";

const log = getLogger("features");
export const DEFAULT_FEATURES_PATH = "config/features.toml";
const SECRET_MARKERS = ["TOKEN", "KEY", "SECRET", "PASSWORD"];

export function loadFeaturesFile(path?: string): Record<string, string> {
  const file = path ?? process.env.FEATURES_FILE ?? DEFAULT_FEATURES_PATH;
  if (!existsSync(file)) return {};
  let data: any;
  try {
    data = Bun.TOML.parse(readFileSync(file, "utf8"));
  } catch (e: any) {
    throw new Error(`Invalid features file ${file}: ${e?.message ?? e}`);
  }
  const table = data.env ?? {};
  if (typeof table !== "object" || Array.isArray(table)) throw new Error(`${file}: [env] must be a table`);
  const out: Record<string, string> = {};
  for (const [name, value] of Object.entries(table)) {
    if (SECRET_MARKERS.some((m) => name.toUpperCase().includes(m))) {
      log.warning(`features file: ignoring secret-like key ${name} (use the environment)`);
      continue;
    }
    out[name] = typeof value === "boolean" ? (value ? "true" : "false") : String(value);
  }
  return out;
}

export function applyFeaturesFile(path?: string, env: Record<string, string | undefined> = process.env): string[] {
  const applied: string[] = [];
  for (const [name, value] of Object.entries(loadFeaturesFile(path))) {
    if (!(name in env)) { env[name] = value; applied.push(name); }
  }
  return applied;
}
