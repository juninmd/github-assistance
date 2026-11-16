#!/usr/bin/env bun
/** Homologation: score the README of each allowlisted repository (read-only). */
import { DEFAULT_MIN_SCORE, needsWork, scoreReadme } from "../src/agents/readme_curator/scoring.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { settingsFromEnv } from "../src/config/settings.ts";
import { GithubClient } from "../src/github/client.ts";

const s = await settingsFromEnv(), gh = new GithubClient(s.githubToken), repos = new RepositoryAllowlist(s.repositoryAllowlistPath).listRepositories();
console.log(`Scoring READMEs for ${repos.length} repositories (min score ${DEFAULT_MIN_SCORE})\n`);
let below = 0;
for (const name of repos) {
  const readme = await gh.getReadme(name).catch(() => null);
  if (!readme) { below++; console.log(`  ${name}: MISSING/ERROR`); continue; }
  const sc = scoreReadme(readme.content), nw = needsWork(sc, DEFAULT_MIN_SCORE);
  if (nw) below++;
  console.log(`  ${name}: ${sc.score}/100 [${nw ? "needs work" : "ok"}] missing: ${sc.missing.join(", ") || "-"}`);
}
console.log(`\n${below}/${repos.length} READMEs abaixo da rubrica (${DEFAULT_MIN_SCORE}).`);
