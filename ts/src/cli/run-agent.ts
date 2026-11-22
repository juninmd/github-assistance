#!/usr/bin/env bun
/** Usage: bun run-agent <agent-name|all> [--pr owner/repo#N] [--ai-provider X] [--ai-model Y] */
import { parseArgs } from "node:util";
import { AGENT_ALIASES, AGENTS_BY_NAME, resolveAgentName } from "../agents/catalog.ts";
import { settingsFromEnv } from "../config/settings.ts";
import { runHealthChecks } from "../health.ts";
import { anyBatchFailure, isFailedResult, runAgent, runAll } from "../run-agent.ts";
import { createBaseDeps } from "../agents/registry.ts";
import { sendExecutionReport } from "../agents/core/reporting.ts";
import { getLogger } from "../utils/logger.ts";

const log = getLogger("run-agent");
const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: { pr: { type: "string" }, "ai-provider": { type: "string" }, "ai-model": { type: "string" } },
});
const name = positionals[0];
if (!name || (name !== "all" && !resolveAgentName(name))) {
  console.error(`usage: run-agent <${[...AGENTS_BY_NAME.keys(), "all"].join("|")}> [--pr owner/repo#N]\nformer names still accepted: ${Object.keys(AGENT_ALIASES).join(", ")}`);
  process.exit(2);
}
const settings = await settingsFromEnv();
const health = runHealthChecks(settings, name);
log.info("Health check results:\n" + health.summary());
if (!health.ok) { log.error("Pre-flight checks failed — aborting agent run"); process.exit(1); }

const opts = { provider: values["ai-provider"], model: values["ai-model"], prRef: values.pr };
let results: Record<string, any> = {};
try {
  results = name === "all" ? await runAll(settings, opts) : await runAgent(name, settings, opts);
} catch (e: any) {
  console.log(`Execution failed: ${e?.message ?? e}`);
  results = { error: String(e?.message ?? e) };
}
try { await sendExecutionReport(createBaseDeps(settings).telegram, name, results); }
catch (e: any) { console.error(`Failed to send Telegram report: ${e?.message ?? e}`); }
process.exit((name === "all" ? anyBatchFailure(results) : isFailedResult(results)) ? 1 : 0);
