import { expect, test } from "bun:test";
import { mapLimit } from "../src/agents/core/utils.ts";
import { checkPipelineStatus } from "../src/agents/pr_assistant/pipeline.ts";

/** Fake client that records how many calls are in flight at once (round-trips overlap instead of queueing). */
function probe() {
  let inflight = 0, peak = 0;
  const call = async <T>(v: T): Promise<T> => { peak = Math.max(peak, ++inflight); await Bun.sleep(10); inflight--; return v; };
  return { call, peak: () => peak };
}
const pr = { head: { sha: "abc" }, base: { repo: { full_name: "o/r" } } };

test("pipeline status fetches statuses, runs and billing annotations concurrently, keeping check order", async () => {
  const p = probe();
  const runs = [1, 2, 3, 4].map((id) => ({ id, name: `job${id}`, conclusion: "failure", status: "completed", output: { summary: "boom", annotations_count: 1 } }));
  const gh: any = {
    getCombinedStatus: () => p.call({ statuses: [] }),
    getCheckRuns: () => p.call(runs),
    paginate: (path: string) => p.call(path.includes("/3/") ? [{ message: "The job was not started because your account payments have failed" }] : []),
  };
  const out = await checkPipelineStatus(gh, pr);
  expect(p.peak()).toBeGreaterThanOrEqual(4);
  expect(out.billing_checks).toEqual(["job3"]);
  expect(out.failed_checks.map((c: any) => c.context)).toEqual(["job1", "job2", "job4"]);
});

test("mapLimit preserves order and never exceeds the limit", async () => {
  const p = probe();
  const out = await mapLimit([5, 4, 3, 2, 1, 0], 2, (n) => p.call(n * 2));
  expect(out).toEqual([10, 8, 6, 4, 2, 0]);
  expect(p.peak()).toBe(2);
  expect(await mapLimit([], 3, async (x) => x)).toEqual([]);
});
