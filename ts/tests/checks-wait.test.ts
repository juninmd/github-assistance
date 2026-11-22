import { expect, test } from "bun:test";
import { mustWaitForChecks } from "../src/agents/pr_assistant/checks-wait.ts";

const now = Date.parse("2026-01-01T12:00:00Z"), min = (n: number) => now - n * 60_000;
const pending = { state: "pending", pending_checks: ["lint", "e2e"] };

test("waits while any check is pending on a fresh head", () => expect(mustWaitForChecks(pending, min(5), now)).toBe(true));
test("stops waiting once stuck checks pass the timeout (billing/queue never finishing)", () => expect(mustWaitForChecks(pending, min(46), now)).toBe(false));
test("no checks at all never waits (no CI)", () => expect(mustWaitForChecks({ state: "success", pending_checks: [], no_ci: true }, min(1), now)).toBe(false));
test("finished checks do not wait", () => expect(mustWaitForChecks({ state: "success", pending_checks: [] }, min(1), now)).toBe(false));
test("unknown head time keeps waiting until next run", () => expect(mustWaitForChecks(pending, null, now)).toBe(true));
test("can be disabled", () => {
  process.env.CHECKS_WAIT_ENABLED = "false";
  try { expect(mustWaitForChecks(pending, min(1), now)).toBe(false); } finally { delete process.env.CHECKS_WAIT_ENABLED; }
});
