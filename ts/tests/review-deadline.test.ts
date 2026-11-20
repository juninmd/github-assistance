import { expect, test } from "bun:test";
import { clearDeadline, deadlineLeftSec, runOpencode, startDeadline } from "../src/agents/pr_assistant/review-workspace.ts";

test("review deadline caps total time and stops further model calls", async () => {
  expect(deadlineLeftSec()).toBe(Infinity);
  const t0 = 1_000_000;
  startDeadline(t0);
  expect(deadlineLeftSec(t0 + 100_000)).toBe(800);
  expect(deadlineLeftSec(t0 + 900_000)).toBe(0);
  startDeadline(Date.now() - 1_000_000);
  expect(await runOpencode("/tmp", "x", "opencode/x-free", 300)).toBeNull();
  clearDeadline();
  expect(deadlineLeftSec()).toBe(Infinity);
});
