import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { JobStore } from "../src/queue/store.ts";
import { settingsFromEnv, type Settings } from "../src/config/settings.ts";

export const tmp = () => mkdtempSync(join(tmpdir(), "ga-"));
export function newStore(dir = tmp(), name = "queue.db") {
  const s = new JobStore(join(dir, name));
  s.initialize();
  return s;
}
export const getJob = (s: JobStore, id: string) => { const j = s.get(id); if (!j) throw new Error("no job"); return j; };
export const testSettings = (over: Record<string, string | undefined> = {}): Promise<Settings> =>
  settingsFromEnv({ GITHUB_TOKEN: "t", FEATURES_FILE: "/nonexistent.toml", ...over });
