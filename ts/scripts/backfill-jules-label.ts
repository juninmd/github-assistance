#!/usr/bin/env bun
/** One-off: label every open issue in the owner's repos 'jules' and assign it to the owner. Dry-run by default; `--apply` writes. */
import { parseArgs } from "node:util";
import { ROADMAP_ACTIVE_LABEL, assignOwner, ensureLabel, issueHasLabel } from "../src/agents/core/utils.ts";
import { GithubClient } from "../src/github/client.ts";

const ACTIVE_COLOR = "6f42c1";
const { values } = parseArgs({ options: { apply: { type: "boolean" } } });
const token = process.env.GITHUB_TOKEN;
if (!token) { console.error("GITHUB_TOKEN is required"); process.exit(1); }
const owner = process.env.GITHUB_OWNER ?? "juninmd", label = ROADMAP_ACTIVE_LABEL, gh = new GithubClient(token);
// Search caps at 1000 results; fail loud instead of silently skipping the rest.
const issues = await gh.paginate(`/search/issues?q=${encodeURIComponent(`is:issue is:open user:${owner} archived:false`)}`, { key: "items", limit: 1000 });
if (issues.length >= 1000) { console.error(`${issues.length} issues exceed the 1000 search cap; split the query`); process.exit(1); }
let labeled = 0, assigned = 0, failed = 0;
const ensured = new Set<string>();
for (const issue of issues) {
  const repo = issue.repository_url.replace(/.*repos\//, "");
  const needsLabel = !issueHasLabel(issue, label), needsAssign = !(issue.assignees ?? []).some((a: any) => a.login.toLowerCase() === owner.toLowerCase());
  if (!needsLabel && !needsAssign) continue;
  console.log(`${repo}#${issue.number} label=${needsLabel} assign=${needsAssign} ${String(issue.title).slice(0, 60)}`);
  if (!values.apply) { if (needsLabel) labeled++; if (needsAssign) assigned++; continue; }
  try {
    if (needsLabel) {
      if (!ensured.has(repo)) { await ensureLabel(gh, repo, label, ACTIVE_COLOR, "Triggers a Jules session", console.log); ensured.add(repo); }
      await gh.addLabelToPr({ ...issue, base: { repo: { full_name: repo } } } as any, label); labeled++;
    }
    if (needsAssign && (await assignOwner(gh, { ...issue, base: { repo: { full_name: repo } } } as any, owner, console.log))) assigned++;
  } catch (e: any) { failed++; console.error(`  FAILED: ${e?.name}: ${e?.message}`); }
}
console.log(`[${values.apply ? "applied" : "dry-run"}] scanned=${issues.length} label=${labeled} assign=${assigned} failed=${failed}`);
process.exit(failed ? 1 : 0);
