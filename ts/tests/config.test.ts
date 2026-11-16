import { expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { AGENT_CATALOG, agentNames } from "../src/agents/catalog.ts";
import { fleetStatus } from "../src/agents/fleet.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { AutonomyPolicy } from "../src/config/autonomy.ts";
import { applyFeaturesFile, loadFeaturesFile } from "../src/config/features.ts";
import { Priorities } from "../src/config/priorities.ts";
import { runResultFromAgentDict } from "../src/results.ts";
import { testSettings, tmp } from "./helpers.ts";

test("features: missing file is noop; env wins; secrets ignored; invalid raises", () => {
  expect(loadFeaturesFile("/nope.toml")).toEqual({});
  const f = join(tmp(), "f.toml");
  writeFileSync(f, '[env]\nQUEUE_MAX_ATTEMPTS = 5\nDASHBOARD_ENABLED = false\nGITHUB_TOKEN = "x"\nAI_MODEL = "m"\n');
  const env: Record<string, string | undefined> = { AI_MODEL: "real" };
  const applied = applyFeaturesFile(f, env);
  expect(env.AI_MODEL).toBe("real");
  expect(env.QUEUE_MAX_ATTEMPTS).toBe("5");
  expect(env.DASHBOARD_ENABLED).toBe("false");
  expect(env.GITHUB_TOKEN).toBeUndefined();
  expect(applied.sort()).toEqual(["DASHBOARD_ENABLED", "QUEUE_MAX_ATTEMPTS"]);
  writeFileSync(f, "[env\nbroken");
  expect(() => loadFeaturesFile(f)).toThrow("Invalid features file");
});

test("settings: defaults, validation, toggles from catalog", async () => {
  const s = await testSettings();
  expect([s.automationMode, s.webhookRetentionDays, s.aiProvider, s.aiModel]).toEqual(["observe", 3, "litellm", "cloud/auto"]);
  expect(Object.keys(s.enabled).length).toBe(AGENT_CATALOG.filter((a) => a.toggleEnv).length);
  expect((await testSettings({ PR_SLA_ENABLED: "off" })).enabled["pr-sla"]).toBe(false);
  expect(testSettings({ QUEUE_MAX_ATTEMPTS: "0" })).rejects.toThrow("QUEUE_MAX_ATTEMPTS must be a positive integer");
  expect(testSettings({ ENABLE_AI: "true", AI_PROVIDER: "nope" })).rejects.toThrow("AI_PROVIDER must be one of");
  expect((await testSettings({ AI_PROVIDER: "ollama" })).aiModel).toBe("qwen3:1.7b");
  expect(settingsFromEnvNoToken()).rejects.toThrow("GITHUB_TOKEN environment variable is required");
});
async function settingsFromEnvNoToken() {
  const { settingsFromEnv } = await import("../src/config/settings.ts");
  return settingsFromEnv({ FEATURES_FILE: "/nonexistent.toml" });
}

test("catalog: unique kebab names; capability filters", () => {
  const names = AGENT_CATALOG.map((a) => a.name);
  expect(new Set(names).size).toBe(names.length);
  for (const n of names) expect(n).toMatch(/^[a-z]+(-[a-z]+)*$/);
  expect(AGENT_CATALOG.length).toBe(17);
  expect(agentNames({ usesJules: true }).has("jules-tracker")).toBe(true);
  expect(agentNames({ requiresAi: false }).has("pr-assistant")).toBe(true);
});

test("fleet explains why an agent cannot run", async () => {
  const s = await testSettings({ CODE_REVIEWER_ENABLED: "false" });
  const by = Object.fromEntries(fleetStatus(s).agents.map((a) => [a.name, a]));
  expect(by["code-reviewer"].blocked_reason).toBe("CODE_REVIEWER_ENABLED=false");
  expect(by["product-manager"].blocked_reason).toBe("ENABLE_AI=false");
  expect(by["pr-assistant"].runnable).toBe(true);
  expect(by["security-scanner"].priority).toBe("critical");
});

test("priorities accumulate across repo, label and title", () => {
  const f = join(tmp(), "p.json");
  writeFileSync(f, JSON.stringify({ repositories: [{ pattern: "^juninmd/core", priority: 10 }], labels: [{ pattern: "security", priority: 5 }], titles: [{ pattern: "fix", priority: 2 }] }));
  const p = new Priorities(f);
  expect(p.priorityFor("juninmd/core#1", { labels: ["security"], title: "fix it" })).toBe(17);
  expect(p.priorityFor("other/x#1", { title: "Fix" })).toBe(0);
  expect(new Priorities("/missing.json").priorityFor("a/b#1")).toBe(0);
});

test("autonomy: defaults observe, per-repo override, merge gate", () => {
  const f = join(tmp(), "a.json");
  writeFileSync(f, JSON.stringify({ defaults: { mode: "suggest" }, repositories: { "Acme/Web": { mode: "merge", merge: true, required_checks: ["ci"] } } }));
  const a = new AutonomyPolicy(f);
  expect(a.forRepository("zzz/q").mode).toBe("suggest");
  expect(a.allowMerge("acme/web")).toBe(true);
  expect(a.allowMerge("zzz/q")).toBe(false);
  expect(a.forRepository("acme/web").required_checks).toEqual(["ci"]);
  expect(new AutonomyPolicy("/missing.json").forRepository("a/b").mode).toBe("observe");
  expect(new AutonomyPolicy(f).toDict().repositories["acme/web"].merge).toBe(true);
});

test("allowlist: repos, owners, invalid entries, save roundtrip", () => {
  const f = join(tmp(), "r.json");
  writeFileSync(f, JSON.stringify({ repositories: ["A/B", 5, ""], users: ["Owner"] }));
  const a = new RepositoryAllowlist(f);
  expect(a.listRepositories()).toEqual(["a/b"]);
  expect(a.isAllowed("owner/anything")).toBe(true);
  expect(a.isAllowed("x/y")).toBe(false);
  expect(a.addRepository("x/y")).toBe(true);
  expect(a.addRepository("X/Y")).toBe(false);
  expect(new RepositoryAllowlist(f).isAllowed("x/y")).toBe(true);
  expect(a.removeRepository("x/y")).toBe(true);
  writeFileSync(f, JSON.stringify({ repositories: "bad" }));
  expect(new RepositoryAllowlist(f).listRepositories()).toEqual([]);
  expect(new RepositoryAllowlist(join(tmp(), "none.json")).isAllowed("a/b")).toBe(false);
});

test("RunResult: counts items from lists, derives status", () => {
  expect(runResultFromAgentDict("x", { merged: [1, 2], skipped: [1] }).items_done).toBe(2);
  expect(runResultFromAgentDict("x", { merged: { a: 1 } }).items_done).toBe(0);
  expect(runResultFromAgentDict("x", { blocked: [1] }).status).toBe("blocked");
  expect(runResultFromAgentDict("x", { pipeline_failures: [1] }).status).toBe("blocked");
  expect(runResultFromAgentDict("x", { failed: [1] }).status).toBe("failed");
  expect(runResultFromAgentDict("x", { error: "e" }).status).toBe("failed");
  expect(runResultFromAgentDict("x", {}).cost).toBeNull();
});
