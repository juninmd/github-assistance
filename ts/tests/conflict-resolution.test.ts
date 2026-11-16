import { afterEach, expect, test } from "bun:test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { cleanAnswer, hasMarkers, parseHunk, resolveHunks, splitKeepEnds, trivialResolution } from "../src/agents/pr_assistant/conflict-hunks.ts";
import { canRegenerate, conflictKinds, conflictPrompt, isLockfile, workflowPushBlocked } from "../src/agents/pr_assistant/conflict-plan.ts";
import { resolveConflictsAutonomously, resolveFileConflictsWithModel, setupCloneEnvironment, tryMergeBase } from "../src/agents/pr_assistant/conflict-resolver.ts";
import { tmp } from "./helpers.ts";

const saved = { ...process.env };
afterEach(() => { for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k]; Object.assign(process.env, saved); });
const sh = async (cwd: string, ...args: string[]) => { const p = Bun.spawn(args, { cwd, stdout: "pipe", stderr: "pipe" }); const out = await new Response(p.stdout).text(); await p.exited; return out.trim(); };

const block = (ours: string, base: string | null, theirs: string) => `<<<<<<< HEAD\n${ours}${base === null ? "" : `||||||| abc123\n${base}`}=======\n${theirs}>>>>>>> upstream/main\n`;
const REAL = block("total = price * qty\n", "total = price\n", "total = price + tax\n");
const FILE = "head1\nhead2\nhead3\n" + REAL + "mid1\nmid2\n" + block("same\n", "old\n", "same\n") + "tail\n";

// --- blocks ---------------------------------------------------------------
test("parseHunk reads both sides and the ancestor; trivial blocks need no model", () => {
  const h = parseHunk(splitKeepEnds(REAL))!;
  expect([h.ours, h.base, h.theirs]).toEqual([["total = price * qty\n"], ["total = price\n"], ["total = price + tax\n"]]);
  expect(parseHunk(splitKeepEnds(block("a\n", null, "b\n")))!.base).toBeNull();
  expect(parseHunk(["<<<<<<< HEAD\n", "x\n", ">>>>>>> b\n"])).toBeNull();
  expect(trivialResolution(h)).toBeNull(); // both sides changed the ancestor differently: needs judgement
  const t = (o: string, b: string | null, th: string) => trivialResolution(parseHunk(splitKeepEnds(block(o, b, th)))!)?.join("");
  expect(t("x = 1\n", "y\n", "x  =  1\n")).toBe("x = 1\n"); // same result on both sides
  expect(t("keep  \n", "keep\n", "changed\n")).toBe("changed\n"); // ours only touched whitespace
  expect(t("changed\n", "keep\n", "keep\n")).toBe("changed\n");
  expect(t("a\n", null, "b\n")).toBeUndefined();
});
test("resolveHunks: asks only for real conflicts and leaves every other byte alone", async () => {
  const seen: string[] = [];
  const r = await resolveHunks(FILE, async (c) => { seen.push(c.pre.join("") + "|" + c.post.join("")); return "total = price * qty + tax\n"; });
  expect(r).toEqual({ text: "head1\nhead2\nhead3\ntotal = price * qty + tax\nmid1\nmid2\nsame\ntail\n", auto: 1, asked: 1 });
  expect(seen).toEqual(["head1\nhead2\nhead3\n|mid1\nmid2\n"]);
  const crlf = await resolveHunks(FILE.replace(/\n/g, "\r\n"), async () => "merged");
  expect(crlf!.text).toBe("head1\r\nhead2\r\nhead3\r\nmerged\r\nmid1\r\nmid2\r\nsame\r\ntail\r\n");
  expect(await resolveHunks("no conflict here\n", async () => "x")).toBeNull();
  expect(await resolveHunks("<<<<<<< HEAD\nx\n", async () => "x")).toBeNull();
});
test("resolveHunks: echoed context is trimmed; unusable answers fail the whole file", async () => {
  const echo = await resolveHunks(FILE, async () => "```ts\nhead2\nhead3\nmerged()\nmid1\nmid2\n```");
  expect(echo!.text).toBe("head1\nhead2\nhead3\nmerged()\nmid1\nmid2\nsame\ntail\n");
  for (const bad of ["", "   ", "CANNOT_RESOLVE", "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> x", "a\n=======\nb", "x".repeat(5000), null])
    expect(await resolveHunks(FILE, async () => bad)).toBeNull();
  const h = parseHunk(splitKeepEnds(REAL))!;
  expect(cleanAnswer("one\ntwo", h, [], [], "\n")).toEqual(["one\n", "two\n"]);
  expect(hasMarkers("a\n||||||| base\nb")).toBe(true); expect(hasMarkers("a ======= b\n|| x")).toBe(false);
});
test("file resolution: model label, deterministic-only, and no model for a real conflict", async () => {
  const prompts: string[] = [];
  const ai: any = { generate: async (p: string) => { prompts.push(p); return "total = price * qty + tax"; } };
  const info = { file: "src/cart.ts", title: "Add quantity", head: "feature", base: "main" };
  const [text, label] = await resolveFileConflictsWithModel(FILE, ai, "p", "m", false, info);
  expect(text).toContain("total = price * qty + tax\n"); expect(hasMarkers(text!)).toBe(false); expect(label).toBe("git-auto, p/m");
  expect(prompts).toHaveLength(1);
  for (const part of ["`src/cart.ts`", "Add quantity", "--- OURS (the pull request, `feature`)\ntotal = price * qty\n", "--- BASE", "total = price\n", "--- THEIRS (the target branch, `main`)\ntotal = price + tax\n", "CANNOT_RESOLVE"]) expect(prompts[0]).toContain(part);
  expect(prompts[0]).not.toContain("<<<<<<<");
  const onlyTrivial = "a\n" + block("same\n", "old\n", "same\n") + "z\n";
  expect(await resolveFileConflictsWithModel(onlyTrivial, null, "p", "m")).toEqual(["a\nsame\nz\n", "git-auto"]);
  expect(await resolveFileConflictsWithModel(FILE, null, "p", "m")).toEqual([null, ""]);
  expect(await resolveFileConflictsWithModel(FILE, { generate: async () => { throw new Error("down"); } } as any, "p", "m")).toEqual([null, ""]);
  expect(conflictPrompt(info, { pre: [], block: [], post: [], hunk: { ours: [], base: null, theirs: ["x\n"] } })).toContain("(vazio: este lado removeu o trecho)");
});
test("lockfiles are regenerated or refused, never merged", () => {
  expect(["web/pnpm-lock.yaml", "bun.lock", "package-lock.json"].every(canRegenerate)).toBe(true);
  expect(["Cargo.lock", "api/poetry.lock", "go.sum"].map((f) => [isLockfile(f), canRegenerate(f)])).toEqual([[true, false], [true, false], [true, false]]);
  expect(isLockfile("src/lock.ts")).toBe(false);
});

// --- end to end on real repositories ----------------------------------------
/** Bare "GitHub" remote with a base commit, a PR branch and a diverged main. */
async function world(o: { feature: (dir: string) => void; main: (dir: string) => void }) {
  const root = tmp(), remote = join(root, "r.git"), seed = join(root, "seed");
  await sh(root, "git", "init", "-q", "--bare", remote);
  await sh(root, "git", "clone", "-q", remote, seed);
  await sh(seed, "git", "config", "user.email", "t@t"); await sh(seed, "git", "config", "user.name", "t"); await sh(seed, "git", "config", "core.autocrlf", "false");
  const commit = async (msg: string, ref: string) => { await sh(seed, "git", "add", "-A"); await sh(seed, "git", "commit", "-qm", msg); await sh(seed, "git", "push", "-q", "origin", `HEAD:${ref}`); };
  writeFileSync(join(seed, "cart.ts"), "import a\ntotal = price\nexport total\n"); writeFileSync(join(seed, "old.ts"), "legacy\n"); writeFileSync(join(seed, "note.md"), "keep\n");
  await commit("base", "main");
  await sh(seed, "git", "checkout", "-q", "-b", "feature"); o.feature(seed); await commit("feat", "feature");
  await sh(seed, "git", "checkout", "-q", "-B", "main", "origin/main"); o.main(seed); await commit("main moves", "main");
  writeFileSync(join(root, "gitconfig"), `[url "file://${remote.replace(/\\/g, "/")}"]\n\tinsteadOf = https://github.com/o/r.git\n[core]\n\tautocrlf = false\n`);
  Object.assign(process.env, { GIT_CONFIG_GLOBAL: join(root, "gitconfig"), GITHUB_TOKEN: "", GH_PAT: "", CONFLICT_OPENCODE_ENABLED: "false", PR_FIX_VALIDATE: "off" });
  const pr = { number: 9, title: "Add quantity", user: { login: "juninmd" }, head: { ref: "feature", repo: { full_name: "o/r" } }, base: { ref: "main", repo: { full_name: "o/r" } } } as any;
  return { root, remote, pr, tip: () => sh(remote, "git", "rev-parse", "feature"), show: (f: string) => sh(remote, "git", "show", `feature:${f}`) };
}
const edit = (file: string, text: string) => (dir: string) => writeFileSync(join(dir, file), text);
const both = (...fs: ((d: string) => void)[]) => (dir: string) => fs.forEach((f) => f(dir));

test("e2e: a real conflict is merged by block and pushed; the rest of the file is untouched", async () => {
  const w = await world({ feature: edit("cart.ts", "import a\ntotal = price * qty\nexport total\n"), main: both(edit("cart.ts", "import a\ntotal = price + tax\nexport total\n"), edit("note.md", "keep\nmain line\n")) });
  const prompts: string[] = [];
  const [ok, msg] = await resolveConflictsAutonomously(w.pr, { aiClient: { generate: async (p: string) => { prompts.push(p); return "total = price * qty + tax"; } } as any, aiProvider: "p", aiModel: "m" });
  expect([ok, msg.split("\n")[0]]).toEqual([true, "Resolved 1 conflict(s) and pushed"]);
  expect(await w.show("cart.ts")).toBe("import a\ntotal = price * qty + tax\nexport total");
  expect(await w.show("note.md")).toBe("keep\nmain line"); // the base's own change came along
  expect(prompts).toHaveLength(1); expect(prompts[0]).toContain("--- BASE (common ancestor, what both sides started from)\ntotal = price\n");
  expect(msg).toContain("p/m"); expect(msg).toContain("no conflict markers");
});
test("e2e: a whitespace-only side needs no model at all", async () => {
  const w = await world({ feature: edit("cart.ts", "import a\ntotal = price  \nexport total\n"), main: edit("cart.ts", "import a\ntotal = price + tax\nexport total\n") });
  const [ok, msg] = await resolveConflictsAutonomously(w.pr, { allowAiFallback: false });
  expect(ok).toBe(true); expect(msg).toContain("git-auto");
  expect(await w.show("cart.ts")).toBe("import a\ntotal = price + tax\nexport total");
});
test("e2e: unsafe conflicts stop before any model call and push nothing", async () => {
  let calls = 0; const ai = { generate: async () => { calls++; return "CANNOT_RESOLVE"; } } as any;
  const deleted = await world({ feature: edit("old.ts", "legacy, edited by the PR\n"), main: (dir) => rmSync(join(dir, "old.ts")) });
  let before = await deleted.tip();
  let [ok, msg] = await resolveConflictsAutonomously(deleted.pr, { aiClient: ai });
  expect(ok).toBe(false); expect(msg).toStartWith("manual-delete-add"); expect(msg).toContain("`old.ts`"); expect(calls).toBe(0); expect(await deleted.tip()).toBe(before);

  const lock = await world({ feature: edit("Cargo.lock", "v = 1\n"), main: edit("Cargo.lock", "v = 2\n") });
  [ok, msg] = await resolveConflictsAutonomously(lock.pr, { aiClient: ai });
  expect(ok).toBe(false); expect(msg).toContain("Lockfile sem regeneração automática: Cargo.lock"); expect(calls).toBe(0);

  const hard = await world({ feature: edit("cart.ts", "import a\ntotal = price * qty\nexport total\n"), main: edit("cart.ts", "import a\ntotal = price + tax\nexport total\n") });
  before = await hard.tip();
  [ok, msg] = await resolveConflictsAutonomously(hard.pr, { aiClient: ai });
  expect(ok).toBe(false); expect(msg).toContain("`cart.ts`"); expect(calls).toBe(1); expect(await hard.tip()).toBe(before);
});
test("e2e: a merge that touches workflows is refused up front when the token lacks the workflow scope", async () => {
  const wf = (dir: string) => { mkdirSync(join(dir, ".github", "workflows"), { recursive: true }); writeFileSync(join(dir, ".github", "workflows", "release.yml"), "on: push\n"); };
  const w = await world({ feature: both(wf, edit("cart.ts", "import a\ntotal = price * qty\nexport total\n")), main: edit("cart.ts", "import a\ntotal = price + tax\nexport total\n") });
  const dir = await setupCloneEnvironment(tmp(), "https://github.com/o/r.git");
  const [rc, , conflicted] = await tryMergeBase(dir, "https://github.com/o/r.git", "feature", "main");
  expect(rc).not.toBe(0); expect(conflicted).toEqual(["cart.ts"]); expect(await conflictKinds(dir)).toEqual({ content: ["cart.ts"], structural: [] });
  const blocked = await workflowPushBlocked(dir, "main", async () => ["repo"]);
  expect(blocked).toContain("escopo `workflow`"); expect(blocked).toContain("`.github/workflows/release.yml`");
  expect(await workflowPushBlocked(dir, "main", async () => ["repo", "workflow"])).toBe("");
  expect(await workflowPushBlocked(dir, "main", async () => null)).toBe(""); // unknown scopes: try, do not guess
  expect(w.pr.number).toBe(9);
});
