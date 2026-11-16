#!/usr/bin/env bun
/** `queue` CLI: worker (--once/--observe), reprocess, list, stats. */
import { parseArgs } from "node:util";
import { settingsFromEnv } from "../config/settings.ts";
import { JobStore } from "../queue/store.ts";
import { QueueWorker, makeObserverHandler } from "../queue/worker.ts";
import { makePrHandler } from "../webhooks/dispatcher.ts";
import { runAgent } from "../run-agent.ts";

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    once: { type: "boolean" }, observe: { type: "boolean" }, pr: { type: "string" },
    status: { type: "string" }, limit: { type: "string", default: "100" }, json: { type: "boolean" },
  },
});
const settings = await settingsFromEnv();
const store = new JobStore(settings.webhookDatabasePath);
store.initialize();

switch (positionals[0]) {
  case "worker": {
    const worker = new QueueWorker(store, values.observe ? makeObserverHandler() : makePrHandler(settings, runAgent), {
      leaseSeconds: settings.queueLeaseSeconds, backoffSeconds: settings.queueBackoffSeconds, limit: settings.maxConcurrentWorkers,
    });
    if (values.once) { console.log(`processed=${await worker.runUntilEmpty()}`); break; }
    console.log(`worker started (poll=${settings.queuePollIntervalSeconds}s); Ctrl+C to stop`);
    process.on("SIGINT", () => { worker.stop(); console.log("\nworker stopped"); process.exit(0); });
    await worker.run(settings.queuePollIntervalSeconds);
    break;
  }
  case "reprocess": {
    if (!values.pr) { console.error("--pr owner/repo#number required"); process.exit(2); }
    console.log(`reprocess ${store.reprocess("pr", values.pr) ? "ok" : "no-op"} for ${values.pr}`);
    break;
  }
  case "list": {
    const jobs = store.list({ status: values.status, limit: Number(values.limit) });
    if (values.json) { console.log(JSON.stringify({ jobs }, null, 2)); break; }
    for (const j of jobs) console.log(`${j.key.padEnd(40)} ${j.status.padEnd(9)} attempts=${j.attempts} decision=${j.decision || "-"}`);
    break;
  }
  case "stats": {
    const s = store.stats();
    if (values.json) { console.log(JSON.stringify(s, null, 2)); break; }
    for (const [k, v] of Object.entries(s).sort()) console.log(`${k.padEnd(10)} ${v}`);
    break;
  }
  default:
    console.error("usage: queue <worker|reprocess|list|stats>");
    process.exit(2);
}
