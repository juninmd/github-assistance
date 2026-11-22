import { createHmac, generateKeyPairSync } from "node:crypto";
import { expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { createApp } from "../src/webhooks/server.ts";
import { GitHubAppAuth, validSignature } from "../src/webhooks/auth.ts";
import { extractPrRefs, makePrHandler } from "../src/webhooks/dispatcher.ts";
import { purgeDeliveries } from "../src/webhooks/retention.ts";
import { DeliveryStore } from "../src/webhooks/store.ts";
import { AuthThrottle } from "../src/webhooks/throttle.ts";
import { connection } from "../src/queue/schema.ts";
import { QueueWorker } from "../src/queue/worker.ts";
import { testSettings, tmp } from "./helpers.ts";

const SECRET = "shh";
const AUTH = { Authorization: "Bearer tok" };
const sign = (b: string) => "sha256=" + createHmac("sha256", SECRET).update(b).digest("hex");

async function appFor(over: Record<string, string | undefined> = {}) {
  const dir = tmp();
  const s = await testSettings({
    WEBHOOK_DATABASE_PATH: join(dir, "w.db"), GITHUB_WEBHOOK_SECRET: SECRET, ADMIN_API_TOKEN: "tok",
    WORKER_ENABLED: "false", PRIORITIES_PATH: join(dir, "none.json"), ...over,
  });
  const app = createApp(s);
  app.store.initialize();
  return { app, s };
}
const hook = (app: any, event: string, payload: any, id = "d1", sig?: string) => {
  const body = JSON.stringify(payload);
  return app.fetch(new Request("http://x/webhooks/github", {
    method: "POST", body, headers: { "x-github-delivery": id, "x-github-event": event, "x-hub-signature-256": sig ?? sign(body) },
  }));
};
const PR = { action: "opened", number: 7, repository: { full_name: "acme/web" }, pull_request: { number: 7 } };
const get = (app: any, path: string, headers: any = AUTH, method = "GET") => app.fetch(new Request("http://x" + path, { method, headers }));

test("signature validation", () => {
  expect(validSignature("b", sign("b"), SECRET)).toBe(true);
  expect(validSignature("b", "sha256=00", SECRET)).toBe(false);
  expect(validSignature("b", null, SECRET)).toBe(false);
  expect(validSignature("b", "md5=1", SECRET)).toBe(false);
});

test("webhook records, enqueues and deduplicates", async () => {
  const { app } = await appFor();
  const r1 = await (await hook(app, "pull_request", PR)).json();
  expect(r1).toEqual({ accepted: true, duplicate: false, mode: "observe", pr_refs: ["acme/web#7"] });
  expect((await (await hook(app, "pull_request", PR)).json()).duplicate).toBe(true);
  expect(app.store.jobs.count()).toBe(1);
});

test("invalid signature, missing headers, unsupported event, bad JSON", async () => {
  const { app } = await appFor();
  expect((await hook(app, "pull_request", PR, "d", "sha256=bad")).status).toBe(401);
  expect((await app.fetch(new Request("http://x/webhooks/github", { method: "POST", body: "{}" }))).status).toBe(400);
  expect(await (await hook(app, "ping", {})).json()).toEqual({ accepted: false, reason: "unsupported_event" });
  const body = "not json";
  expect((await app.fetch(new Request("http://x/webhooks/github", { method: "POST", body, headers: { "x-github-delivery": "z", "x-github-event": "pull_request", "x-hub-signature-256": sign(body) } }))).status).toBe(400);
});

test("bot issue_comment does not enqueue; redelivered hook does not reopen finished job", async () => {
  const { app } = await appFor();
  const c = { repository: { full_name: "a/b" }, issue: { number: 1, pull_request: {} }, sender: { type: "Bot" } };
  expect((await (await hook(app, "issue_comment", c, "bot1")).json()).pr_refs).toEqual([]);
  await hook(app, "pull_request", PR, "d1");
  const job = app.store.jobs.list()[0];
  app.store.jobs.complete(job.id, "succeeded");
  await hook(app, "pull_request", PR, "d1");
  expect(app.store.jobs.get(job.id)!.status).toBe("succeeded");
});

test("event during processing marks re-evaluation; priority from config", async () => {
  const dir = tmp();
  writeFileSync(join(dir, "p.json"), JSON.stringify({ repositories: [{ pattern: "acme", priority: 9 }] }));
  const { app } = await appFor({ PRIORITIES_PATH: join(dir, "p.json") });
  await hook(app, "pull_request", PR, "d1");
  const [j] = app.store.jobs.list();
  expect(j.priority).toBe(9);
  app.store.jobs.claim();
  await hook(app, "pull_request", PR, "d2");
  expect(app.store.jobs.get(j.id)!.reprocess_pending).toBe(true);
});

test("record_and_enqueue is atomic", async () => {
  const { app } = await appFor();
  const store = app.store;
  const orig = store.jobs.upsert.bind(store.jobs);
  store.jobs.upsert = () => { throw new Error("boom"); };
  expect(() => store.recordAndEnqueue("d9", "pull_request", PR, ["acme/web#7"], { mode: "observe" })).toThrow("boom");
  store.jobs.upsert = orig;
  expect(connection(store.path).query("SELECT COUNT(*) AS n FROM deliveries").get()).toEqual({ n: 0 });
});

test("admin API: disabled without token, 401, filters, detail, reprocess, bulk, overview, agents", async () => {
  const off = await appFor({ ADMIN_API_TOKEN: "" });
  expect((await get(off.app, "/api/jobs")).status).toBe(403);
  const { app } = await appFor();
  expect((await get(app, "/api/jobs", {})).status).toBe(401);
  expect((await get(app, "/api/jobs", {}, "POST")).status).toBe(401);
  await hook(app, "pull_request", PR, "d1");
  await hook(app, "pull_request", { ...PR, number: 8, pull_request: { number: 8 }, repository: { full_name: "acme/api" } }, "d2");
  const page = await (await get(app, "/api/jobs?limit=1")).json();
  expect([page.total, page.jobs.length]).toEqual([2, 1]);
  expect((await (await get(app, "/api/jobs?repo=acme/api")).json()).total).toBe(1);
  expect((await (await get(app, "/api/jobs?q=API")).json()).jobs[0].key).toBe("acme/api#8");
  expect(await (await get(app, "/api/jobs?status=blocked")).json()).toEqual({ jobs: [], total: 0 });
  expect((await get(app, "/api/jobs?status=bogus")).status).toBe(422);
  expect((await get(app, "/api/jobs?limit=501")).status).toBe(422);
  const id = page.jobs[0].id;
  expect((await (await get(app, `/api/jobs/${id}`)).json()).id).toBe(id);
  expect((await get(app, "/api/jobs/missing")).status).toBe(404);
  expect((await get(app, "/api/jobs/missing/reprocess", AUTH, "POST")).status).toBe(404);
  app.store.jobs.claim(Date.now() / 1000 + 1, 2);
  expect((await get(app, `/api/jobs/${id}/reprocess`, AUTH, "POST")).status).toBe(409);
  app.store.jobs.complete(id, "blocked", { error: "boom" });
  const errored = app.store.jobs.list({ status: "blocked" }).length;
  expect(await (await get(app, "/api/jobs/reprocess-errored", AUTH, "POST")).json()).toEqual({ requeued: errored, found: errored });
  const reset = await (await get(app, `/api/jobs/${id}/reprocess`, AUTH, "POST")).json();
  expect([reset.status, reset.attempts]).toEqual(["pending", 0]);
  const ov = await (await get(app, "/api/overview?hours=48")).json();
  expect(ov.window_hours).toBe(48);
  expect(ov.deliveries).toEqual([{ label: "pull_request", value: 2 }]);
  expect(ov.service).toEqual({ mode: "observe", simulation: false, worker_enabled: false, worker_alive: false, poll_interval_seconds: 15 });
  expect((await get(app, "/api/overview?hours=0")).status).toBe(422);
  expect((await get(app, "/api/overview?hours=9999")).status).toBe(422);
  const fleet = await (await get(app, "/api/agents")).json();
  expect(fleet.agents.length).toBe(8);
});

test("admin: bad tokens throttled; responses not cacheable", async () => {
  const { app } = await appFor();
  for (let i = 0; i < 10; i++) expect((await get(app, "/api/overview", { Authorization: "Bearer x" })).status).toBe(401);
  const blocked = await get(app, "/api/overview", { Authorization: "Bearer x" });
  expect(blocked.status).toBe(429);
  expect(Number(blocked.headers.get("Retry-After"))).toBeGreaterThanOrEqual(1);
  const ok = await appFor();
  const r = await get(ok.app, "/api/overview");
  expect(r.headers.get("Cache-Control")).toBe("no-store");
  expect(r.headers.get("X-Content-Type-Options")).toBe("nosniff");
});

test("throttle window expires", () => {
  let t = 0;
  const th = new AuthThrottle(2, 60, () => t);
  th.recordFailure("a"); th.recordFailure("a");
  expect(th.retryAfter("a")).toBeGreaterThan(0);
  expect(th.retryAfter("b")).toBe(0);
  t = 61;
  expect(th.retryAfter("a")).toBe(0);
});

test("dashboard: strict CSP, redirect, 404, can be disabled, assets self-contained", async () => {
  const { app } = await appFor();
  const root = await get(app, "/", {});
  expect([root.status, new URL(root.headers.get("location")!).pathname]).toEqual([307, "/dashboard/"]);
  const page = await get(app, "/dashboard/", {});
  expect(page.status).toBe(200);
  expect(await page.text()).toContain("Central de Controle");
  const csp = page.headers.get("content-security-policy")!;
  expect(csp).toContain("default-src 'none'");
  expect(csp).not.toContain("'unsafe-inline'");
  expect(page.headers.get("cache-control")).toBe("no-cache");
  const js = await get(app, "/dashboard/js/main.js", {});
  expect(js.status).toBe(200);
  expect(js.headers.get("content-type")).toContain("javascript");
  expect((await get(app, "/dashboard/missing.js", {})).status).toBe(404);
  expect((await get(app, "/dashboard/../package.json", {})).status).toBe(404);
  const off = await appFor({ DASHBOARD_ENABLED: "false" });
  expect((await get(off.app, "/dashboard/", {})).status).toBe(404);
  expect((await get(off.app, "/api/jobs")).status).toBe(200);
});

test("health endpoints", async () => {
  const { app } = await appFor();
  expect(await (await get(app, "/health/live", {})).json()).toEqual({ status: "ok" });
  expect((await get(app, "/health/ready", {})).status).toBe(503);
});

test("extract PR refs", () => {
  expect(extractPrRefs("pull_request", PR)).toEqual(["acme/web#7"]);
  expect(extractPrRefs("check_suite", { repository: { full_name: "a/b" }, check_suite: { pull_requests: [{ number: 3 }, { number: 1 }] } })).toEqual(["a/b#1", "a/b#3"]);
  expect(extractPrRefs("issue_comment", { repository: { full_name: "a/b" }, issue: { number: 2 } })).toEqual([]);
  expect(extractPrRefs("issue_comment", { repository: { full_name: "a/b" }, issue: { number: 2, pull_request: {} } })).toEqual(["a/b#2"]);
  expect(extractPrRefs("pull_request", {})).toEqual([]);
});

test("PR handler: observe mode has no effects; autonomous maps results", async () => {
  const s = await testSettings({ AUTOMATION_MODE: "autonomous" });
  const job: any = { key: "a/b#1", payload: {} };
  const run = (r: any) => makePrHandler(s, async () => r, async () => "tok")(job);
  expect(await makePrHandler({ ...s, automationMode: "observe" }, async () => { throw new Error("no"); })({ ...job, payload: { mode: "observe" } })).toMatchObject({ decision: "observed" });
  expect(await run({ error: "x" })).toMatchObject({ status: "failed", next_action: "retry" });
  expect(await run({ blocked: [{ reason: "mergeable_state_unknown: x" }] })).toMatchObject({ status: "failed", decision: "blocked" });
  expect(await run({ blocked: [{ reason: "ci_failed" }], _run_result: { status: "blocked" } })).toMatchObject({ status: "succeeded", decision: "blocked" });
});

test("retention: batches, keeps recent, dedupe after purge", async () => {
  const { app } = await appFor();
  const st: DeliveryStore = app.store;
  const db = connection(st.path);
  for (let i = 0; i < 7; i++) db.query("INSERT INTO deliveries (delivery_id,event,payload,received_at) VALUES (?,?,?,?)").run(`old${i}`, "pull_request", "{}", "2020-01-01 00:00:00");
  db.query("INSERT INTO deliveries (delivery_id,event,payload) VALUES ('new','pull_request','{}')").run();
  const r = purgeDeliveries(st.path, 3, { batch: 3 });
  expect(r.deleted).toBe(7);
  expect((db.query("SELECT COUNT(*) AS n FROM deliveries").get() as any).n).toBe(1);
  expect((await (await hook(app, "pull_request", PR, "old0")).json()).duplicate).toBe(false);
  expect((await (await hook(app, "pull_request", PR, "new")).json()).duplicate).toBe(true);
});

test("GitHub App JWT: string issuer, RS256 structure; token is cached", async () => {
  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048, privateKeyEncoding: { type: "pkcs8", format: "pem" }, publicKeyEncoding: { type: "spki", format: "pem" } });
  const f = join(tmp(), "k.pem");
  writeFileSync(f, privateKey);
  const a = new GitHubAppAuth(123, 9, f);
  const [h, p, sig] = a.jwt().split(".");
  expect(JSON.parse(Buffer.from(h, "base64url").toString()).alg).toBe("RS256");
  expect(JSON.parse(Buffer.from(p, "base64url").toString()).iss).toBe("123");
  expect(sig.length).toBeGreaterThan(100);
  let calls = 0;
  const real = globalThis.fetch;
  globalThis.fetch = (async () => { calls++; return Response.json({ token: "ghs_x" }); }) as any;
  try {
    expect(await a.installationToken()).toBe("ghs_x");
    expect(await a.installationToken()).toBe("ghs_x");
    expect(calls).toBe(1);
  } finally { globalThis.fetch = real; }
});

test("worker end-to-end: webhook -> observe job processed", async () => {
  const { app, s } = await appFor();
  await hook(app, "pull_request", PR);
  const w = new QueueWorker(app.store.jobs, makePrHandler(s, async () => ({})), { limit: 1 });
  expect(await w.runUntilEmpty()).toBe(1);
  expect(app.store.jobs.list()[0]).toMatchObject({ status: "succeeded", decision: "observed" });
});
