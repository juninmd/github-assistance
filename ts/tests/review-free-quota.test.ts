import { afterEach, expect, test } from "bun:test";
import { candidateModels, freeExhausted, isFreeQuotaError, markFreeExhausted, resetFreeQuota } from "../src/agents/pr_assistant/review-models.ts";

afterEach(() => resetFreeQuota());

test("free-tier quota error is recognised from opencode output", () => {
  expect(isFreeQuotaError('{"type":"error","error":{"type":"FreeUsageLimitError","message":"Free usage limit reached."}}')).toBe(true);
  expect(isFreeQuotaError("connection reset")).toBe(false);
});
test("once the account free quota is spent, only the cloud model is a candidate (no doomed per-model retries)", async () => {
  markFreeExhausted();
  expect(freeExhausted()).toBe(true);
  const c = await candidateModels();
  expect(c).toHaveLength(1);
  expect(c[0]!.endsWith("-free")).toBe(false);
});
test("quota backoff expires", () => {
  markFreeExhausted(Date.now() - 2 * 60 * 60_000);
  expect(freeExhausted()).toBe(false);
});
