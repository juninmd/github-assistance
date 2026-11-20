import { expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { run } from "../src/utils/proc.ts";
import { validateChanges } from "../src/agents/pr_assistant/pipeline-fixer.ts";
import { churnReason, whitespaceChurn } from "../src/agents/pr_assistant/fix-churn.ts";
import { tmp } from "./helpers.ts";

// livro-do-dia#5: the review fix re-indented a whole file to change one line, breaking biome.
const src = Array.from({ length: 40 }, (_, i) => `  const v${i} = ${i};`).join("\n") + "\n";
async function repo(): Promise<string> {
  const dir = tmp();
  for (const a of [["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]]) await run(["git", ...a], { cwd: dir });
  writeFileSync(join(dir, "a.ts"), src);
  await run(["git", "add", "-A"], { cwd: dir }); await run(["git", "commit", "-qm", "init"], { cwd: dir });
  return dir;
}

test("a fix that re-indents the file around a one-line change is rejected", async () => {
  const dir = await repo();
  writeFileSync(join(dir, "a.ts"), src.replace(/^ {2}/gm, "    ").replace("v3 = 3", "v3 = 33"));
  expect((await whitespaceChurn(dir)).whitespace).toBeGreaterThanOrEqual(39);
  const [ok, reason] = await validateChanges(dir, ["a.ts"]);
  expect(ok).toBe(false);
  expect(reason).toContain("whitespace");
});
test("a focused fix passes", async () => {
  const dir = await repo();
  writeFileSync(join(dir, "a.ts"), src.replace("v3 = 3", "v3 = 33"));
  expect(await whitespaceChurn(dir)).toEqual({ total: 2, whitespace: 0 });
  expect((await validateChanges(dir, ["a.ts"]))[0]).toBe(true);
});
test("churnReason reads staged changes for the review-fix commit path", async () => {
  const dir = await repo();
  writeFileSync(join(dir, "a.ts"), src.replace(/^ {2}/gm, "\t"));
  expect(await churnReason(dir, true)).toBe("");
  await run(["git", "add", "-A"], { cwd: dir });
  expect(await churnReason(dir, true)).toContain("whitespace-only");
});
