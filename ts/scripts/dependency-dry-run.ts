#!/usr/bin/env bun
/** Homologation: detect dependency ecosystems for the allowlisted repos (read-only; no branch/issue/PR). */
import { detectEcosystems, ecosystemSummary, rootFilenames } from "../src/agents/dependency_manager/detect.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { settingsFromEnv } from "../src/config/settings.ts";
import { GithubClient } from "../src/github/client.ts";

const s = await settingsFromEnv(), gh = new GithubClient(s.githubToken), repos = new RepositoryAllowlist(s.repositoryAllowlistPath).listRepositories();
console.log(`Detecting dependency ecosystems for ${repos.length} allowlisted repositories\n`);
let actionable = 0;
for (const name of repos) {
  try {
    const repo = await gh.getRepo(name);
    const ecos = detectEcosystems(rootFilenames(await gh.getTreePaths(name, repo.default_branch)));
    if (ecos.length) { actionable++; console.log(`  ${name}: ${ecos.map(ecosystemSummary).join(", ")}`); } else console.log(`  ${name}: no dependencies`);
  } catch (e: any) { console.log(`  ${name}: ERROR ${e?.name}: ${e?.message}`); }
}
console.log(`\n${actionable}/${repos.length} repositorios teriam um PR de dependencias.`);
