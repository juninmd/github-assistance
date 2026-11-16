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
