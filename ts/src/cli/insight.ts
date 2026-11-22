#!/usr/bin/env bun
/** `pr-insight explain|history|cost` — queryable view over PR merge decisions and LLM cost. */
import { parseArgs } from "node:util";
import { settingsFromEnv } from "../config/settings.ts";
import { explainPr, jobHistory } from "../insight/explain.ts";
import { summarize, summarizeSkills, summarizeTokenix } from "../insight/cost.ts";

const { values, positionals } = parseArgs({ allowPositionals: true, options: { pr: { type: "string" }, json: { type: "boolean" }, limit: { type: "string" }, hours: { type: "string" } } });
const cmd = positionals[0];
const out = (o: unknown) => console.log(JSON.stringify(o, (_, v) => v, 2));
if (cmd === "cost") {
  const log = process.env.AI_USAGE_LOG ?? "", hours = values.hours === undefined ? undefined : Number(values.hours);
  if (hours !== undefined && !(Number.isFinite(hours) && hours > 0)) { console.error("--hours must be a positive number"); process.exit(2); }
  const rows = summarize(log, hours), skills = summarizeSkills(log, hours), tokenix = summarizeTokenix(log, hours);
  if (values.json) out({ cost: rows, skills, tokenix });
  else {
    for (const r of rows) console.log(`${r.agent.padEnd(28)} runs=${String(r.runs).padEnd(4)} calls=${String(r.calls).padEnd(5)} tokens~${String(r.tokens).padEnd(9)} saved~${r.tokens_saved} (cache hits ${r.cache_hits})`);
    for (const r of skills) console.log(`${r.harness.padEnd(22)} skill=${r.skill.padEnd(24)} runs=${r.runs}`);
    for (const [n, g] of Object.entries(tokenix)) if (g.runs) console.log(`opencode ${(n + " tokenix").padEnd(15)} runs=${String(g.runs).padEnd(4)} mean_tokens~${g.mean_tokens} tokenix_calls=${g.tokenix_calls}`);
  }
} else if (cmd === "explain" || cmd === "history") {
  const s = await settingsFromEnv();
  if (cmd === "explain") {
    if (!values.pr) { console.error("--pr owner/repo#number required"); process.exit(2); }
    const r = await explainPr(s, values.pr);
    if (values.json) out(r);
    else { console.log(`PR: ${r.pr_ref}  state=${r.state} merged=${r.merged}`); console.log(`autonomy=${r.autonomy_mode} pipeline=${r.pipeline_state}`); console.log("reasons:"); for (const x of r.reasons ?? []) console.log(`  - ${x}`); }
  } else {
    const rows = jobHistory(s, values.pr, values.limit ? Number(values.limit) : 50);
    if (values.json) out({ history: rows });
    else for (const r of rows as any[]) console.log(`${Math.round(r.created_at)} ${String(r.status).padEnd(9)} attempts=${r.attempts} decision=${r.decision || "-"} next=${r.next_action || "-"} ${r.key}`);
  }
} else { console.error("usage: pr-insight <explain --pr owner/repo#N | history [--pr ..] | cost [--hours N]> [--json]"); process.exit(2); }
