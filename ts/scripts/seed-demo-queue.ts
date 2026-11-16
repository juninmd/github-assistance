#!/usr/bin/env bun
/**
 * Seed a throwaway queue database with realistic demo data for the dashboard (deterministic seed; refuses a DB that has jobs).
 *   bun scripts/seed-demo-queue.ts --db /tmp/demo/webhooks.db
 *   ADMIN_API_TOKEN=demo WEBHOOK_DATABASE_PATH=/tmp/demo/webhooks.db WORKER_ENABLED=false GITHUB_TOKEN=x bun src/webhooks/server.ts
 */
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { parseArgs } from "node:util";
import { connection } from "../src/queue/schema.ts";
import { DeliveryStore } from "../src/webhooks/store.ts";

const REPOS = ["octo-demo/storefront", "octo-demo/billing-api", "octo-demo/design-system", "octo-demo/mobile-app", "octo-demo/infra-k8s",
  "octo-demo/data-pipeline", "octo-demo/docs-site", "octo-demo/auth-service", "octo-demo/notifier", "octo-demo/search-indexer"];
const EVENTS: [string, number][] = [["pull_request", 34], ["check_suite", 27], ["workflow_run", 22], ["pull_request_review", 11], ["issue_comment", 6]];
const BLOCK_REASONS = ["ci_failed: 2 checks failing on head SHA", "review_rejected: evaluator returned REJECT", "merge_conflicts: branch cannot be updated against base"];
const RETRY_ERRORS = ["GitHub API 502 Bad Gateway while fetching check runs", "pipeline evidence still pending after update_pr_branch"];
const HOUR = 3600;

/** mulberry32: small deterministic PRNG so screenshots are reproducible. */
function rng(seed: number) {
  let a = seed;
  const random = () => { a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  return {
    random, uniform: (lo: number, hi: number) => lo + (hi - lo) * random(),
    choice: <T>(xs: readonly T[]) => xs[Math.floor(random() * xs.length)]!,
    expo: (lambda: number) => -Math.log(1 - random()) / lambda,
    weighted: <T>(xs: readonly T[], w: readonly number[]) => { let r = random() * w.reduce((a, b) => a + b, 0); for (let i = 0; i < xs.length; i++) { if ((r -= w[i]!) < 0) return xs[i]!; } return xs.at(-1)!; },
    bits: () => Array.from({ length: 5 }, () => Math.floor(random() * 2 ** 32).toString(16).padStart(8, "0")).join(""),
  };
}
type R = ReturnType<typeof rng>;
function ageSeconds(r: R, now: number): number {
  const age = r.expo(1 / (20 * HOUR));
  const hour = new Date((now - age) * 1000).getUTCHours();
  const busy = 0.55 + 0.45 * Math.sin(((hour - 7) / 24) * 2 * Math.PI);
  return r.random() < busy ? age : age + r.uniform(2, 9) * HOUR;
}
function job(r: R, index: number, now: number) {
  const repo = r.weighted(REPOS, REPOS.map((_, i) => REPOS.length - i));
  let updated = now - Math.min(ageSeconds(r, now), 7 * 24 * HOUR - 60), created = updated - r.uniform(40, 900);
  const roll = r.random();
  let status = "succeeded", attempts = 1, decision: string | null = "merge", action: string | null = "none", error: string | null = null, nextRun = updated;
  if (roll < 0.14) { status = "blocked"; decision = "blocked"; action = "fix"; error = r.choice(BLOCK_REASONS); attempts = r.choice([1, 3, 3]); }
  else if (roll < 0.19) { status = "pending"; attempts = r.choice([1, 2]); decision = "wait"; action = "retry"; error = r.choice(RETRY_ERRORS); nextRun = now + r.uniform(-200, 240); }
  else if (roll < 0.215) { status = "pending"; attempts = 0; decision = null; action = null; updated = now - r.uniform(20, 1500); created = updated; nextRun = updated; }
  else if (roll < 0.42) { decision = "observed"; action = "observe"; }
  const payload = { mode: "autonomous", event: r.choice(EVENTS)[0], action: "synchronize" };
  return [index.toString(16).padStart(32, "0"), "pr", `${repo}#${100 + index}`, JSON.stringify(payload), r.choice([0, 0, 0, 5]), status, attempts, 3, nextRun, repo, r.bits(), decision, action, error, created, updated];
}
export function seed(path: string, jobs = 460, now = Date.now() / 1000): { jobs: number; deliveries: number } {
  const r = rng(7);
  mkdirSync(dirname(path), { recursive: true });
  new DeliveryStore(path).initialize();
  const db = connection(path);
  if ((db.query("SELECT COUNT(*) AS n FROM jobs").get() as any).n) throw new Error(`${path} already has jobs; refusing to seed over real data`);
  const insJob = db.prepare("INSERT INTO jobs (id, kind, key, payload, priority, status, attempts, max_attempts, next_run_at, repo, sha, decision, next_action, last_error, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
  const insDel = db.prepare("INSERT INTO deliveries (delivery_id, event, action, repository, payload, received_at) VALUES (?,?,?,?,?,?)");
  const rows = Array.from({ length: jobs }, (_, i) => job(r, i, now));
  const deliveries = Array.from({ length: jobs * 3 }, (_, i) => [`demo-${i}`, r.weighted(EVENTS.map((e) => e[0]), EVENTS.map((e) => e[1])), "synchronize", r.choice(REPOS), "{}",
    new Date((now - r.uniform(0, 3 * 24 * HOUR)) * 1000).toISOString().slice(0, 19).replace("T", " ")]);
  db.transaction(() => {
    for (const j of rows) insJob.run(...(j as any[]));
    db.query("UPDATE jobs SET status='running', lease_token='demo', lease_expires_at=?, updated_at=? WHERE id IN (SELECT id FROM jobs WHERE status='pending' ORDER BY attempts LIMIT 2)").run(now + 240, now - 35);
    for (const d of deliveries) insDel.run(...(d as any[]));
  }).immediate();
  return { jobs, deliveries: deliveries.length };
}
if (import.meta.main) {
  const { values } = parseArgs({ options: { db: { type: "string" }, jobs: { type: "string", default: "460" } } });
  if (!values.db) { console.error("--db <path> required"); process.exit(2); }
  console.log(JSON.stringify(seed(values.db, Number(values.jobs))));
}
