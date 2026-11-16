/** HTTP entrypoint: GitHub webhooks, admin API (/api/*), dashboard, durable queue worker. */
import { explainPr } from "../insight/explain.ts";
import { join, normalize, resolve } from "node:path";
import { timingSafeEqual } from "node:crypto";
import { existsSync } from "node:fs";
import { fleetStatus } from "../agents/fleet.ts";
import { Priorities } from "../config/priorities.ts";
import { settingsFromEnv, type Settings } from "../config/settings.ts";
import { MAX_WINDOW_HOURS, queueOverview } from "../queue/overview.ts";
import { JobStore } from "../queue/store.ts";
import { QueueWorker } from "../queue/worker.ts";
import { runAgent } from "../run-agent.ts";
import { getLogger } from "../utils/logger.ts";
import { GitHubAppAuth, validSignature } from "./auth.ts";
import { extractPrRefs, makePrHandler } from "./dispatcher.ts";
import { startRetention } from "./retention.ts";
import { DeliveryStore } from "./store.ts";
import { AuthThrottle } from "./throttle.ts";

const log = getLogger("webhook-server");
export const MAX_PAYLOAD_BYTES = 2 * 1024 * 1024;
export const SUPPORTED_EVENTS = new Set(["check_suite", "issue_comment", "pull_request", "pull_request_review", "workflow_run"]);
const JOB_STATUSES = new Set(["pending", "running", "succeeded", "failed", "blocked"]);
const STATIC_DIR = resolve(import.meta.dir, "../../static");
const SECURITY_HEADERS = {
  "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-cache",
};
const json = (data: unknown, status = 200, headers: Record<string, string> = {}) =>
  Response.json(data, { status, headers });
const err = (status: number, detail: string, headers: Record<string, string> = {}) => json({ detail }, status, headers);

function intParam(u: URL, name: string, d: number, min: number, max: number): number | null {
  const raw = u.searchParams.get(name);
  if (raw === null) return d;
  const n = Number(raw);
  return Number.isInteger(n) && n >= min && n <= max ? n : null;
}

export type App = { fetch: (req: Request, ip?: string) => Promise<Response>; store: DeliveryStore; start(): void; stop(): void };

export function createApp(config: Settings): App {
  const store = new DeliveryStore(config.webhookDatabasePath);
  const priorities = new Priorities(config.prioritiesPath);
  const throttle = new AuthThrottle();
  let worker: QueueWorker | null = null;
  let workerAlive = false;
  let stopPurge: (() => void) | null = null;

  const configured = () => {
    const { githubAppId: a, githubInstallationId: i, githubAppPrivateKeyPath: k, githubWebhookSecret: s } = config;
    if (!a || !i || !k || !s) return false;
    try { new GitHubAppAuth(a, i, k).jwt(); return true; } catch { return false; }
  };

  async function admin(req: Request, url: URL, ip: string): Promise<Response> {
    const base = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
    const fail = (s: number, d: string, h: Record<string, string> = {}) => err(s, d, { ...base, ...h });
    const token = config.adminApiToken;
    if (!token) return fail(403, "admin API disabled");
    const wait = throttle.retryAfter(ip);
    if (wait) return fail(429, "too many failed attempts", { "Retry-After": String(wait) });
    const given = Buffer.from(req.headers.get("authorization") ?? ""), want = Buffer.from(`Bearer ${token}`);
    if (!given.length || given.length !== want.length || !timingSafeEqual(given, want)) {
      throttle.recordFailure(ip);
      log.warning("Admin auth failed", { client: ip });
      return fail(401, "invalid token", { "WWW-Authenticate": "Bearer" });
    }
    throttle.reset(ip);
    const ok = (d: unknown, s = 200) => json(d, s, base);
    const path = url.pathname.replace(/^\/api/, "");
    const method = req.method;

    if (path === "/jobs" && method === "GET") {
      const status = url.searchParams.get("status") ?? undefined;
      if (status && !JOB_STATUSES.has(status)) return fail(422, "invalid status");
      const limit = intParam(url, "limit", 100, 1, 500), offset = intParam(url, "offset", 0, 0, 1e9);
      const repo = url.searchParams.get("repo") ?? undefined, q = url.searchParams.get("q") ?? undefined;
      if (limit === null || offset === null || (repo?.length ?? 0) > 200 || (q?.length ?? 0) > 200) return fail(422, "invalid query");
      const f = { status, repo, search: q };
      return ok({ jobs: store.jobs.list({ ...f, limit, offset }), total: store.jobs.count(f) });
    }
    if (path === "/jobs/reprocess-errored" && method === "POST") {
      const limit = intParam(url, "limit", 100, 1, 500);
      if (limit === null) return fail(422, "invalid limit");
      const jobs = store.jobs.list({ status: "blocked", limit }).filter((j) => j.last_error);
      const requeued = jobs.filter((j) => store.jobs.reprocess(j.kind, j.key)).length;
      log.info("Admin bulk reprocess", { found: jobs.length, requeued });
      return ok({ requeued, found: jobs.length });
    }
    const m = path.match(/^\/jobs\/([^/]+)(\/reprocess)?$/);
    if (m) {
      const job = store.jobs.get(m[1]);
      if (!job) return fail(404, "job not found");
      if (!m[2] && method === "GET") return ok(job);
      if (m[2] && method === "POST") {
        if (job.status === "running") return fail(409, "job is running");
        store.jobs.reprocess(job.kind, job.key);
        log.info("Admin reprocess", { job: job.id, kind: job.kind, key: job.key });
        return ok(store.jobs.get(job.id));
      }
    }
    if (path === "/overview" && method === "GET") {
      const hours = intParam(url, "hours", 24, 1, MAX_WINDOW_HOURS);
      if (hours === null) return fail(422, "invalid hours");
      return ok({
        ...queueOverview(store.path, { hours }), deliveries: store.eventCounts(hours),
        service: { mode: config.automationMode, simulation: config.simulationMode, worker_enabled: config.workerEnabled,
          worker_alive: workerAlive, poll_interval_seconds: config.queuePollIntervalSeconds },
      });
    }
    if (path === "/agents" && method === "GET") return ok(fleetStatus(config));
    const ex = path.match(/^\/prs\/([^/]+)\/([^/]+)\/(\d+)\/explain$/);
    if (ex && method === "GET") return ok(await explainPr(config, `${ex[1]}/${ex[2]}#${ex[3]}`));
    return fail(404, "not found");
  }

  async function webhook(req: Request): Promise<Response> {
    const delivery = req.headers.get("x-github-delivery"), event = req.headers.get("x-github-event");
    if (!delivery || !event) return err(400, "missing GitHub headers");
    const body = new Uint8Array(await req.arrayBuffer());
    if (body.length > MAX_PAYLOAD_BYTES) return err(413, "payload too large");
    if (!config.githubWebhookSecret || !validSignature(body, req.headers.get("x-hub-signature-256"), config.githubWebhookSecret)) return err(401, "invalid signature");
    let payload: any;
    try { payload = JSON.parse(new TextDecoder().decode(body)); } catch { return err(400, "invalid JSON"); }
    if (!SUPPORTED_EVENTS.has(event)) return json({ accepted: false, reason: "unsupported_event" });
    let prRefs = extractPrRefs(event, payload);
    if (event === "issue_comment" && payload.sender?.type === "Bot") prRefs = [];
    const [created] = store.recordAndEnqueue(delivery, event, payload, prRefs, {
      mode: config.automationMode, priority: Math.max(0, ...prRefs.map((r) => priorities.priorityFor(r))),
    });
    log.info("Webhook persisted", { delivery, event, duplicate: !created });
    return json({ accepted: true, duplicate: !created, mode: config.automationMode, pr_refs: prRefs });
  }

  async function serveStatic(pathname: string): Promise<Response> {
    let rel = normalize(decodeURIComponent(pathname.replace(/^\/dashboard\/?/, ""))) || "index.html";
    if (rel.endsWith("/") || rel === ".") rel = join(rel, "index.html");
    const file = resolve(STATIC_DIR, rel);
    if (!file.startsWith(STATIC_DIR) || !existsSync(file)) return err(404, "not found");
    return new Response(Bun.file(file), { headers: SECURITY_HEADERS });
  }

  async function handle(req: Request, ip = "unknown"): Promise<Response> {
    const url = new URL(req.url);
    const p = url.pathname;
    if (p === "/health/live") return json({ status: "ok" });
    if (p === "/health/ready") return configured() && store.ready() ? json({ status: "ready", mode: config.automationMode }) : err(503, "service not ready");
    if (p.startsWith("/api/") && !p.includes("..")) return admin(req, url, ip);
    if (p === "/webhooks/github" && req.method === "POST") return webhook(req);
    if (config.dashboardEnabled) {
      if (p === "/") return Response.redirect(new URL("/dashboard/", url), 307);
      if (p === "/dashboard") return Response.redirect(new URL("/dashboard/", url), 307);
      if (p.startsWith("/dashboard/") && (req.method === "GET" || req.method === "HEAD")) return serveStatic(p);
    }
    return err(404, "Not Found");
  }

  return {
    fetch: handle, store,
    start() {
      store.initialize();
      if (config.workerEnabled) {
        worker = new QueueWorker(new JobStore(config.webhookDatabasePath), makePrHandler(config, runAgent), {
          leaseSeconds: config.queueLeaseSeconds, backoffSeconds: config.queueBackoffSeconds, limit: config.maxConcurrentWorkers,
        });
        workerAlive = true;
        void worker.run(config.queuePollIntervalSeconds).finally(() => { workerAlive = false; });
        log.info("Durable queue worker started", { db: config.webhookDatabasePath });
      }
      if (config.webhookPurgeEnabled) stopPurge = startRetention(config.webhookDatabasePath, config.webhookRetentionDays, config.webhookPurgeIntervalSeconds);
    },
    stop() { worker?.stop(); stopPurge?.(); },
  };
}

if (import.meta.main) {
  const config = await settingsFromEnv();
  const app = createApp(config);
  app.start();
  const server = Bun.serve({
    port: Number(process.env.PORT ?? 8080), hostname: "0.0.0.0",
    maxRequestBodySize: MAX_PAYLOAD_BYTES + 1024,
    fetch: (req, srv) => app.fetch(req, srv.requestIP(req)?.address ?? "unknown"),
  });
  log.info(`listening on :${server.port}`);
  for (const sig of ["SIGTERM", "SIGINT"] as const) process.on(sig, () => { app.stop(); server.stop(); process.exit(0); });
}
