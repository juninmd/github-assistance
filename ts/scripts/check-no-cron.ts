#!/usr/bin/env bun
/** Fail CI if a prohibited cron-scheduled GitHub Actions workflow is added. `--list` prints triggers without failing. */
import { basename } from "node:path";
import { parseArgs } from "node:util";
import { APPROVED_SCHEDULED_WORKFLOWS, detectCronWorkflows } from "../src/agents/security_scanner/workflow-policy.ts";

const { values } = parseArgs({ options: { "repo-dir": { type: "string", default: "." }, list: { type: "boolean" } } });
const violations = detectCronWorkflows(values["repo-dir"]!, values.list ? new Set() : APPROVED_SCHEDULED_WORKFLOWS);
if (!violations.length) { console.log("✅ No prohibited cron-scheduled workflows found."); process.exit(0); }
if (values.list) {
  console.log(`Found ${violations.length} cron trigger(s):`);
  for (const v of violations) console.log(`  ${v.file}:${v.line}  cron: ${v.cron}${APPROVED_SCHEDULED_WORKFLOWS.has(basename(v.file)) ? " (approved)" : ""}`);
  process.exit(0);
}
console.log(`❌ ${violations.length} prohibited cron-scheduled workflow trigger(s) found:\n`);
for (const v of violations) console.log(`  ${v.file}:${v.line}  ->  cron: ${v.cron}`);
console.log("\nScheduled (cron) GitHub Actions are prohibited because they consume runner minutes continuously, even on idle repos.\nUse `workflow_dispatch` or event-driven triggers instead, or delegate periodic work to the central orchestrator.");
process.exit(1);
