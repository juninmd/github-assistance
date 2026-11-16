import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Glob } from "bun";

const ROOT = join(import.meta.dir, "..", "..");
// Standard/ambient variables that are not project configuration.
const IGNORED = new Set(["GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "AI_CACHE", "HOME", "PATH", "PWD", "NODE_OPTIONS", "NODE_ENV", "TMPDIR", "XDG_CONFIG_HOME"]);

test("every env var read in src/ is documented in .env.example", () => {
  const used = new Set<string>();
  const re = /(?:process\.env|\benv)(?:\.([A-Z][A-Z0-9_]+)|\[\s*["']([A-Za-z0-9_]+)["']\s*\])/g;
  const also = /envInt\(\s*["']([A-Z0-9_]+)|truthy\(\s*["']([A-Z0-9_]+)|enabled\(\s*["']([A-Z0-9_]+)/g;
  for (const f of new Glob("**/*.ts").scanSync({ cwd: join(ROOT, "ts", "src"), absolute: true })) {
    const text = readFileSync(f, "utf8");
    for (const m of text.matchAll(re)) used.add(m[1] ?? m[2]!);
    for (const m of text.matchAll(also)) used.add(m[1] ?? m[2] ?? m[3]!);
  }
  const documented = new Set([...readFileSync(join(ROOT, ".env.example"), "utf8").matchAll(/^#?\s*([A-Za-z_0-9]+)=/gm)].map((m) => m[1]!));
  const missing = [...used].filter((v) => !documented.has(v) && !IGNORED.has(v)).sort();
  expect(missing).toEqual([]);
});
