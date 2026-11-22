import { afterEach, expect, test } from "bun:test";
import { chmodSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { applyGate, gateEnabled } from "../src/agents/pr_assistant/review-gate.ts";
import { runProjectChecks, detectCommands } from "../src/agents/pr_assistant/build-check.ts";
import * as rv from "../src/agents/pr_assistant/review-verdict.ts";
import { tmp } from "./helpers.ts";

const saved = { ...process.env };
afterEach(() => { for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k]; Object.assign(process.env, saved); });
const parse = (t: string, model = "") => rv.parseReview(t, model)!;

test("parse: approve, fenced changes with findings, synonyms, invalid, bad entries", () => {
  const a = parse('{"verdict":"APPROVE","summary":"Tudo certo"}', "m");
  expect(rv.isApproved(a)).toBe(true); expect(a.model).toBe("m"); expect(rv.verdictLabel(a)).toBe(rv.LABEL_APPROVED);
  const c = parse('Segue a analise:\n```json\n{"verdict":"REQUEST_CHANGES","summary":"Bug","findings":[{"file":"a.py","line":"10","severity":"error","issue":"crash"}]}\n```');
  expect(c.verdict).toBe(rv.REQUEST_CHANGES); expect(c.findings[0]).toMatchObject({ file: "a.py", line: 10, severity: "error" }); expect(rv.verdictLabel(c)).toBe(rv.LABEL_CHANGES);
  expect(parse('{"verdict":"LGTM"}').verdict).toBe(rv.APPROVE); expect(parse('{"decision":"rejected"}').verdict).toBe(rv.REQUEST_CHANGES);
  for (const bad of [null, "", "no json here", '{"verdict":"MAYBE"}']) expect(rv.parseReview(bad as any)).toBeNull();
  const f = parse('{"verdict":"APPROVE","findings":["x",{"issue":"y"}]}'); expect(f.findings).toHaveLength(1); expect(f.findings[0]!.line).toBe(0);
});
test("comment rendering", () => {
  const ok = rv.buildReviewComment(parse('{"verdict":"APPROVE","summary":"Muito bom"}', "litellm/cloud/auto"), "abcdef123456");
  for (const s of [rv.REVIEW_MARKER, "✅", "Muito bom", "abcdef12", "github-assistance", "Sem pontos bloqueantes"]) expect(ok).toContain(s);
  expect(ok).not.toContain("### 🛠️ Correções");
  const ch = rv.buildReviewComment(parse('{"verdict":"REQUEST_CHANGES","summary":"Corrigir","findings":[{"file":"b.py","line":3,"severity":"warn","issue":"vaza segredo"}]}'));
  for (const s of ["❌", "**Resumo:** Corrigir", "### 🔎 Achados", "### 🛠️ Correções", "Nenhuma correção automática", "b.py", "vaza segredo", "|---"]) expect(ch).toContain(s);
  const fixed = rv.buildReviewComment({ ...parse('{"verdict":"REQUEST_CHANGES","findings":[{"file":"a.py"}]}'), fixed: true, commit: "deadbeef1234" });
  expect(fixed).toContain("Correções aplicadas"); expect(fixed).toContain("deadbeef"); expect(fixed).not.toContain("Nenhuma correção automática");
  const crit = rv.buildReviewComment(parse('{"verdict":"REQUEST_CHANGES","findings":[{"file":"a.py","severity":"error","issue":"x"}]}'));
  for (const s of ["🚨 Crítico", "github-assistance/review"]) expect(crit).toContain(s);
});
test("critical and blocks(min severity)", () => {
  const w = parse('{"verdict":"REQUEST_CHANGES","findings":[{"severity":"warn"}]}'), e = parse('{"verdict":"REQUEST_CHANGES","findings":[{"severity":"error"}]}'), n = parse('{"verdict":"REQUEST_CHANGES","findings":[{"severity":"nit"}]}');
  expect(rv.isCritical(e)).toBe(true); expect(rv.isCritical(n)).toBe(false);
  expect(rv.blocks(w, "warn")).toBe(true); expect(rv.blocks(w, "error")).toBe(false); expect(rv.blocks(e)).toBe(true); expect(rv.blocks(e, "nit")).toBe(true);
  expect(rv.blocks(parse('{"verdict":"APPROVE"}'), "nit")).toBe(false);
});

// --- gate ----------------------------------------------------------------
const prx = (draft = false) => ({ number: 7, draft, head: { sha: "sha123" }, base: { repo: { full_name: "o/r" } } }) as any;
const verdict = (sev: string, v: string) => rv.mkVerdict({ verdict: v, summary: "x", model: "m", findings: [rv.mkFinding({ file: "a.py", line: 1, severity: sev, issue: "issue" })] });
function gh(over: any = {}) {
  const calls: any[] = [];
  return { calls, getLabels: async () => [], createLabel: async () => {}, addLabelToPr: async (_p: any, l: string) => { calls.push(["label", l]); },
    createStatus: async (_r: string, _s: string, o: any) => { calls.push(["status", o.state, o.context]); }, setDraft: async (_p: any, d: boolean) => { calls.push(["draft", d]); },
    removeLabel: async (_p: any, l: string) => { calls.push(["unlabel", l]); }, ...over } as any;
}
test("gate: disabled noop; critical drafts+failure; approve success+ready", async () => {
  let g = gh(); await applyGate(prx(), g, verdict("error", rv.REQUEST_CHANGES), false, () => {}); expect(g.calls).toEqual([]);
  g = gh(); await applyGate(prx(), g, verdict("error", rv.REQUEST_CHANGES), true, () => {});
  expect(g.calls).toEqual([["draft", true], ["label", rv.LABEL_CRITICAL], ["status", "failure", rv.GATE_NAME]]);
  g = gh(); await applyGate(prx(true), g, verdict("warn", rv.APPROVE), true, () => {});
  expect(g.calls).toEqual([["status", "success", rv.GATE_NAME], ["draft", false], ["unlabel", rv.LABEL_CRITICAL]]);
});
test("gate: drafts even if status fails; min severity", async () => {
  const logs: string[] = [], g = gh({ createStatus: async () => { throw new Error("app only"); } });
  await applyGate(prx(), g, verdict("error", rv.REQUEST_CHANGES), true, (m) => logs.push(m));
  expect(g.calls[0]).toEqual(["draft", true]); expect(logs.length).toBeGreaterThan(0);
  const g2 = gh(); await applyGate(prx(), g2, verdict("warn", rv.REQUEST_CHANGES), true, () => {}, "warn"); expect(g2.calls[0]).toEqual(["draft", true]);
  const g3 = gh(); await applyGate(prx(), g3, verdict("warn", rv.REQUEST_CHANGES), true, () => {}); expect(g3.calls).toEqual([]);
  delete process.env.REVIEW_GATE_ENABLED; expect(gateEnabled()).toBe(true); process.env.REVIEW_GATE_ENABLED = "false"; expect(gateEnabled()).toBe(false);
});

// --- build check (fake npm on PATH) --------------------------------------
async function project(npmScript: string) {
  const dir = tmp(), bin = tmp();
  writeFileSync(join(bin, "npm"), `#!/bin/sh\n${npmScript}\n`); chmodSync(join(bin, "npm"), 0o755);
  process.env.PATH = `${bin}:${saved.PATH}`;
  const proj = join(dir, "p"); mkdirSync(join(proj, "node_modules"), { recursive: true });
  writeFileSync(join(proj, "package.json"), '{"scripts":{"test":"x"}}');
  await Bun.spawn(["git", "init", "-q", proj]).exited;
  return proj;
}
test("build check: off, nothing runnable, failing, passing, env skip, artifacts removed", async () => {
  const empty = tmp(); await Bun.spawn(["git", "init", "-q", empty]).exited;
  process.env.PR_FIX_VALIDATE = "off"; expect(await runProjectChecks(empty)).toEqual([true, "build gate off"]);
  delete process.env.PR_FIX_VALIDATE;
  const [ok0, m0] = await runProjectChecks(empty); expect(ok0).toBe(true); expect(m0).toContain("skipped");
  let p = await project("echo boom; exit 1"); let [ok, msg] = await runProjectChecks(p); expect(ok).toBe(false); expect(msg).toStartWith("npm test failed");
  p = await project("exit 0"); [ok, msg] = await runProjectChecks(p); expect(ok).toBe(true); expect(msg).toContain("passed: npm test");
  p = await project("echo 'sh: 1: vite: not found' ; echo 'command not found' ; exit 1"); [ok, msg] = await runProjectChecks(p); expect(ok).toBe(true); expect(msg).toContain("env");
  p = await project("echo 1 > out.bin"); [ok] = await runProjectChecks(p); expect(ok).toBe(true); expect(existsSync(join(p, "out.bin"))).toBe(false);
});
test("build check: detects go and cargo when tools exist", () => {
  const dir = tmp(), bin = tmp();
  for (const t of ["go", "cargo"]) { writeFileSync(join(bin, t), "#!/bin/sh\n"); chmodSync(join(bin, t), 0o755); }
  process.env.PATH = `${bin}:${saved.PATH}`;
  writeFileSync(join(dir, "go.mod"), "module x\n"); writeFileSync(join(dir, "Cargo.toml"), "[package]\n");
  expect(detectCommands(dir).map(([l]) => l)).toEqual(["go build", "cargo check"]);
});
