import { expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { run } from "../src/utils/proc.ts";
import { validateChanges } from "../src/agents/pr_assistant/pipeline-fixer.ts";
import { brokenTemplates, literalReason } from "../src/agents/pr_assistant/fix-literals.ts";
import { tmp } from "./helpers.ts";

// livro-do-dia#5: the review fix turned `Olá, ${nome}` into "Olá, ${nome}", so the page printed the literal placeholder.
const src = "export const hi = (nome: string) => `Olá, ${nome}!`;\nexport const n = 1;\n";
async function repo(): Promise<string> {
  const dir = tmp();
  for (const a of [["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]]) await run(["git", ...a], { cwd: dir });
  writeFileSync(join(dir, "a.ts"), src);
  writeFileSync(join(dir, "notes.md"), "use `x ${y}`\n");
  await run(["git", "add", "-A"], { cwd: dir }); await run(["git", "commit", "-qm", "init"], { cwd: dir });
  return dir;
}

test("brokenTemplates flags an interpolation moved from a template literal into a quoted string", () => {
  const diff = "--- a/a.ts\n+++ b/a.ts\n@@ -1 +1 @@\n-const s = `Olá, ${nome}!`;\n+const s = \"Olá, ${nome}!\";\n";
  expect(brokenTemplates(diff)).toEqual(["a.ts: \"Olá, ${nome}!\""]);
});
test("brokenTemplates ignores quotes inside a template, untouched templates and non-JS files", () => {
  const nested = "--- a/a.ts\n+++ b/a.ts\n@@ -1 +1 @@\n-const s = `${a}`;\n+const s = `\"${a}\"`;\n";
  const kept = "--- a/a.ts\n+++ b/a.ts\n@@ -1 +1 @@\n-const s = `${a}`;\n+const s = `${a}!`;\n";
  const md = "--- a/n.md\n+++ b/n.md\n@@ -1 +1 @@\n-use `x ${y}`\n+use \"x ${y}\"\n";
  const fresh = "--- a/a.ts\n+++ b/a.ts\n@@ -1 +1 @@\n-x\n+const tpl = \"${HOME}/bin\";\n";
  for (const d of [nested, kept, md, fresh, ""]) expect(brokenTemplates(d)).toEqual([]);
});
test("a fix that turns a template literal into a plain string is rejected", async () => {
  const dir = await repo();
  writeFileSync(join(dir, "a.ts"), src.replace("`Olá, ${nome}!`", "\"Olá, ${nome}!\""));
  const [ok, reason] = await validateChanges(dir, ["a.ts"]);
  expect(ok).toBe(false);
  expect(reason).toContain("template literal");
});
test("literalReason reads the index for the review-fix commit path; a real fix passes", async () => {
  const dir = await repo();
  writeFileSync(join(dir, "a.ts"), src.replace("`Olá, ${nome}!`", "'Olá, ${nome}!'"));
  expect(await literalReason(dir, true)).toBe("");
  await run(["git", "add", "-A"], { cwd: dir });
  expect(await literalReason(dir, true)).toContain("a.ts");
  const ok = await repo();
  writeFileSync(join(ok, "a.ts"), src.replace("n = 1", "n = 2"));
  expect(await validateChanges(ok, ["a.ts"])).toEqual([true, expect.anything()]);
});
