import { expect, test } from "bun:test";
import { join } from "node:path";
import { explainPr, jobHistory } from "../src/insight/explain.ts";
import { tmp, testSettings } from "./helpers.ts";

test("explain: invalid ref, unavailable PR, live decision", async () => {
  const dir = tmp();
  const s = await testSettings({ WEBHOOK_DATABASE_PATH: join(dir, "w.db"), AUTONOMY_POLICY_PATH: "/nonexistent.json" });
  expect((await explainPr(s, "nohash")).reasons).toEqual(["invalid_pr_ref"]);
  const down: any = { getPull: async () => { throw new Error("404"); } };
  const r1 = await explainPr(s, "o/r#1", down);
  expect(r1.reasons[0]).toContain("pr_unavailable"); expect(r1.autonomy_mode).toBe("observe");
  const gh: any = { getPull: async () => ({ state: "open", mergeable: false, merged_at: null, head: { sha: "abc" }, base: { repo: { full_name: "o/r" } } }),
    getCombinedStatus: async () => ({ statuses: [] }), getCheckRuns: async () => [{ name: "ci", status: "completed", conclusion: "success" }] };
  const r2 = await explainPr(s, "o/r#1", gh);
  expect(r2.pipeline_state).toBe("success"); expect(r2.reasons).toContain("merge_conflicts"); expect(r2.reasons).toContain("autonomy_mode:observe"); expect(r2.decision).toBe("blocked");
  expect(jobHistory(s, "o/r#1")).toEqual([]);
});

// NaN or a non-positive window used to be read as "no window" and printed all-time totals as if they were the last N hours.
test("pr-insight cost rejects a --hours value that is not a positive number", () => {
  const cli = join(import.meta.dir, "../src/cli/insight.ts");
  const run = (h: string) => Bun.spawnSync(["bun", cli, "cost", `--hours=${h}`], { env: { ...process.env, AI_USAGE_LOG: "/nonexistent" } });
  for (const bad of ["abc", "0", "-5"]) {
    const r = run(bad);
    expect(r.exitCode).toBe(2);
    expect(r.stderr.toString()).toContain("--hours");
  }
  expect(run("24").exitCode).toBe(0);
});
