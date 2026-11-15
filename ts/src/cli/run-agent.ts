#!/usr/bin/env bun
/** Usage: bun run-agent <agent-name|all> [--pr owner/repo#N] [--ai-provider X] [--ai-model Y] */
import { parseArgs } from "node:util";
import { AGENTS_BY_NAME } from "../agents/catalog.ts";
import { settingsFromEnv } from "../config/settings.ts";
import { runHealthChecks } from "../health.ts";
import { isFailedResult, runAgent } from "../run-agent.ts";
import { getLogger } from "../utils/logger.ts";

const log = getLogger("run-agent");
const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: { pr: { type: "string" }, "ai-provider": { type: "string" }, "ai-model": { type: "string" } },
});
const name = positionals[0];
if (!name || (name !== "all" && !AGENTS_BY_NAME.has(name))) {
  console.error(`usage: run-agent <${[...AGENTS_BY_NAME.keys(), "all"].join("|")}> [--pr owner/repo#N]`);
  process.exit(2);
}
const settings = await settingsFromEnv();
const health = runHealthChecks(settings, name);
log.info("Health check results:\n" + health.summary());
if (!health.ok) { log.error("Pre-flight checks failed — aborting agent run"); process.exit(1); }

let failed = false;
const opts = { provider: values["ai-provider"], model: values["ai-model"], prRef: values.pr };
if (name === "all") {
  for (const spec of AGENTS_BY_NAME.values()) {
    if (!spec.inBatch || settings.enabled[spec.name] === false) continue;
    failed = isFailedResult(await runAgent(spec.name, settings, opts)) || failed;
  }
} else {
  failed = isFailedResult(await runAgent(name, settings, opts));
}
process.exit(failed ? 1 : 0);
