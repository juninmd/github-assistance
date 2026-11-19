import { expect, test } from "bun:test";
import { forbiddenPaths, isForbiddenPath } from "../src/agents/pr_assistant/forbidden-paths.ts";
import { validateChanges } from "../src/agents/pr_assistant/pipeline-fixer.ts";
import { tmp } from "./helpers.ts";

// Bot fixes committed a .pyc and tried to commit node_modules/.env; those must never reach a PR.
test("isForbiddenPath flags artifacts, deps and env files", () => {
  for (const p of ["a/__pycache__/m.cpython-312.pyc", "m.pyc", "x.pyo", "node_modules/x/i.js", "web/node_modules/a", ".env", "api/.env.local", "a\\node_modules\\b"]) expect(isForbiddenPath(p)).toBe(true);
});
test("isForbiddenPath keeps source and env templates", () => {
  for (const p of ["src/app.py", ".env.example", "cfg/.env.sample", "docs/node_modules.md", "environment.ts", "pyc.txt"]) expect(isForbiddenPath(p)).toBe(false);
  expect(forbiddenPaths([])).toEqual([]);
});
test("validateChanges rejects a fix that touches forbidden paths", async () => {
  const [ok, reason] = await validateChanges(tmp(), ["src/a.ts", "node_modules/x/i.js", ".env"]);
  expect(ok).toBe(false);
  expect(reason).toContain("node_modules/x/i.js");
  expect(reason).toContain(".env");
});
