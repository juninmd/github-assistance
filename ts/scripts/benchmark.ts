#!/usr/bin/env bun
/**
 * Reproducible micro-benchmarks for the durable queue, webhook API and CLI cold start.
 *   bun scripts/benchmark.ts --out bench.json
 *   bun scripts/benchmark.ts --compare base.json head.json     # markdown table
 */
import { createHmac } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseArgs } from "node:util";
import { settingsFromEnv } from "../src/config/settings.ts";
import { jobHistory } from "../src/insight/explain.ts";
import { connection } from "../src/queue/schema.ts";
import { JobStore } from "../src/queue/store.ts";
import { QueueWorker, makeObserverHandler } from "../src/queue/worker.ts";
import { createApp } from "../src/webhooks/server.ts";

const SEED_ROWS = 20_000, STATUSES = ["succeeded", "succeeded", "succeeded", "blocked", "failed", "pending"];
const COLD_START = ["src/cli/run-agent.ts", "src/agents/pr_assistant/agent.ts", "src/cli/insight.ts", "src/cli/queue.ts", "src/webhooks/server.ts"];
type Stat = { median_ms: number; p95_ms: number };
const round = (n: number, d = 4) => Math.round(n * 10 ** d) / 10 ** d;

async function timed(fn: () => unknown, repeat: number): Promise<Stat> {
  const samples: number[] = [];
  for (let i = 0; i < repeat; i++) { const t = performance.now(); await fn(); samples.push(performance.now() - t); }
  samples.sort((a, b) => a - b);
  const mid = samples.length >> 1, median = samples.length % 2 ? samples[mid]! : (samples[mid - 1]! + samples[mid]!) / 2;
  return { median_ms: round(median), p95_ms: round(samples[Math.min(samples.length - 1, Math.floor(samples.length * 0.95))]!) };
}
function seedRows(path: string, rows: number) {
  const db = connection(path), now = Date.now() / 1000;
  const ins = db.prepare("INSERT INTO jobs (id, kind, key, payload, priority, status, attempts, max_attempts, next_run_at, repo, decision, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)");
  db.transaction(() => { for (let i = 0; i < rows; i++) { const t = now - (rows - i) * 130; ins.run(i.toString(16).padStart(32, "0"), "pr", `acme/repo-${i % 200}#${i}`, "{}", i % 3, STATUSES[i % STATUSES.length]!, 1, 3, t, `acme/repo-${i % 200}`, i % 2 ? "merge" : "wait", t, t + 40); } })();
}
async function benchQueue(tmp: string): Promise<Record<string, Stat>> {
  const out: Record<string, Stat> = {}, path = join(tmp, "queue.db"), store = new JobStore(path);
  store.initialize(); seedRows(path, SEED_ROWS);
  let n = 0;
  out["enqueue (new job)"] = await timed(() => store.enqueue("pr", `bench/new#${n++}`, { mode: "observe" }), 300);
  out["enqueue (coalesce existing)"] = await timed(() => store.enqueue("pr", "bench/new#1", { mode: "observe" }), 300);
  out["list_jobs (latest 100)"] = await timed(() => store.list({ limit: 100 }), 60);
  out["list_jobs (status=blocked, 100)"] = await timed(() => store.list({ status: "blocked", limit: 100 }), 60);
  out["stats (count by status)"] = await timed(() => store.stats(), 60);
  out["job_history (one PR)"] = await timed(() => jobHistory({ webhookDatabasePath: path }, "acme/repo-7#7", 50), 60);
  out["claim + complete (1 job)"] = await timed(() => { for (const j of store.claim()) store.complete(j.id, "succeeded", { lease_token: j.lease_token }); }, 300);
  const drain = new JobStore(join(tmp, "drain.db")); drain.initialize();
  for (let i = 0; i < 500; i++) drain.enqueue("pr", `bench/drain#${i}`, {});
  const t = performance.now(), processed = await new QueueWorker(drain, makeObserverHandler(), { limit: 10 }).runUntilEmpty();
  out[`worker drain (${processed} jobs)`] = { median_ms: round(performance.now() - t, 2), p95_ms: 0 };
  return out;
}
async function benchWebhook(tmp: string): Promise<Record<string, Stat>> {
  const s = await settingsFromEnv({ GITHUB_TOKEN: "x", GITHUB_WEBHOOK_SECRET: "bench-secret", ADMIN_API_TOKEN: "bench-admin", WEBHOOK_DATABASE_PATH: join(tmp, "webhook.db"), WORKER_ENABLED: "false", FEATURES_FILE: "/nonexistent.toml" });
  const app = createApp(s); app.store.initialize();
  let n = 0;
  const post = async () => {
    const i = n++, body = JSON.stringify({ action: "synchronize", number: i, pull_request: { number: i }, repository: { full_name: `acme/repo-${i % 20}` } });
    const res = await app.fetch(new Request("http://x/webhooks/github", { method: "POST", body, headers: { "X-GitHub-Delivery": `d-${i}`, "X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=" + createHmac("sha256", "bench-secret").update(body).digest("hex") } }));
    if (!res.ok) throw new Error(`webhook ${res.status}`);
  };
  const list = async () => { const r = await app.fetch(new Request("http://x/api/jobs?limit=100", { headers: { Authorization: "Bearer bench-admin" } })); if (!r.ok) throw new Error(`jobs ${r.status}`); await r.text(); };
  return { "POST /webhooks/github": await timed(post, 300), "GET /api/jobs?limit=100": await timed(list, 60) };
}
async function benchColdStart(): Promise<Record<string, Stat>> {
  const out: Record<string, Stat> = {}, root = join(import.meta.dir, "..");
  for (const m of COLD_START) out[`cold import ${m}`] = await timed(async () => { const p = Bun.spawn([process.execPath, "-e", `await import(${JSON.stringify(join(root, m).replace(/\\/g, "/"))})`], { cwd: root, stdout: "ignore", stderr: "ignore", env: { ...process.env, GITHUB_TOKEN: "x" } }); await p.exited; }, 7);
  return out;
}
function compare(basePath: string, headPath: string) {
  const base = JSON.parse(readFileSync(basePath, "utf8")).results, head = JSON.parse(readFileSync(headPath, "utf8")).results;
  console.log("| Scenario | Before (ms) | After (ms) | Speedup |\n|---|---:|---:|---:|");
  for (const [name, after] of Object.entries<Stat>(head)) {
    const before = base[name] as Stat | undefined;
    if (!before) { console.log(`| ${name} | n/a | ${after.median_ms.toFixed(3)} | new |`); continue; }
    console.log(`| ${name} | ${before.median_ms.toFixed(3)} | ${after.median_ms.toFixed(3)} | ${(after.median_ms ? before.median_ms / after.median_ms : 0).toFixed(2)}x |`);
  }
}
const { values } = parseArgs({ options: { out: { type: "string" }, compare: { type: "string", multiple: true } } });
if (values.compare?.length === 2) compare(values.compare[0]!, values.compare[1]!);
else {
  const tmp = mkdtempSync(join(tmpdir(), "bench-"));
  try {
    const results = { ...(await benchQueue(tmp)), ...(await benchWebhook(tmp)), ...(await benchColdStart()) };
    const text = JSON.stringify({ seed_rows: SEED_ROWS, bun: Bun.version, results }, null, 2);
    if (values.out) writeFileSync(values.out, text, "utf8");
    console.log(text);
  } finally { rmSync(tmp, { recursive: true, force: true }); }
}
