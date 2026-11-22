import { expect, test } from "bun:test";
import { unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { run } from "../src/utils/proc.ts";
import { validateChanges } from "../src/agents/pr_assistant/pipeline-fixer.ts";
import { deletionReason } from "../src/agents/pr_assistant/fix-deletions.ts";
import { tmp } from "./helpers.ts";

// zplint#44: the review fix replaced 155 lines of src/fix.rs with 15 and gutted the feature.
const src = Array.from({ length: 155 }, (_, i) => `fn f${i}() -> u32 { ${i} }`).join("\n") + "\n";
async function repo(): Promise<string> {
  const dir = tmp();
  for (const a of [["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]]) await run(["git", ...a], { cwd: dir });
  writeFileSync(join(dir, "fix.rs"), src);
  writeFileSync(join(dir, "other.rs"), "fn x() {}\n");
  await run(["git", "add", "-A"], { cwd: dir }); await run(["git", "commit", "-qm", "init"], { cwd: dir });
  return dir;
}
const gut = (dir: string) => writeFileSync(join(dir, "fix.rs"), src.split("\n").slice(0, 15).join("\n") + "\nfn stub() {}\n");

test("a fix that guts a file is rejected", async () => {
  const dir = await repo();
  gut(dir);
  const [ok, reason] = await validateChanges(dir, ["fix.rs"]);
  expect(ok).toBe(false);
  expect(reason).toContain("fix.rs (-140/+1)");
});
test("a focused fix passes", async () => {
  const dir = await repo();
  writeFileSync(join(dir, "fix.rs"), src.replace("f3() -> u32 { 3 }", "f3() -> u32 { 33 }"));
  expect(await deletionReason(dir)).toBe("");
});
test("removing a small block in proportion passes", async () => {
  const dir = await repo();
  writeFileSync(join(dir, "fix.rs"), src.split("\n").slice(30).join("\n"));
  expect(await deletionReason(dir)).toBe("");
});
test("deleting a tracked file is rejected", async () => {
  const dir = await repo();
  unlinkSync(join(dir, "other.rs"));
  expect(await deletionReason(dir)).toContain("deletes tracked file(s) other.rs");
});
test("the staged diff is checked before commit", async () => {
  const dir = await repo();
  gut(dir);
  expect(await deletionReason(dir, true)).toBe("");
  await run(["git", "add", "-A"], { cwd: dir });
  expect(await deletionReason(dir, true)).toContain("fix.rs");
});
