import { describe, expect, test } from "bun:test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SecurityScannerAgent } from "../src/agents/security_scanner/agent.ts";
import { sanitizeFindings } from "../src/agents/security_scanner/scanner.ts";
import { detectCronWorkflows, scanWorkflowText } from "../src/agents/security_scanner/workflow-policy.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { tmp } from "./helpers.ts";

describe("workflow policy", () => {
  test("detects cron entries, strips quotes/comments", () => {
    const v = scanWorkflowText('on:\n  schedule:\n    - cron: "0 9 * * *"  # daily\n    - cron: 5 4 * * 1 # w\n  push:\n', "w.yml");
    expect(v).toEqual([{ file: "w.yml", line: 3, cron: "0 9 * * *" }, { file: "w.yml", line: 4, cron: "5 4 * * 1" }]);
  });
  test("skips approved workflow, sorts, ignores non-yaml", () => {
    const d = tmp(); const wf = join(d, ".github/workflows"); mkdirSync(wf, { recursive: true });
    writeFileSync(join(wf, "b.yml"), "- cron: '1 1 * * *'\n"); writeFileSync(join(wf, "a.yaml"), "- cron: '2 2 * * *'\n");
    writeFileSync(join(wf, "daily-project-creator.yml"), "- cron: '3 3 * * *'\n"); writeFileSync(join(wf, "x.txt"), "- cron: '4 4 * * *'\n");
    expect(detectCronWorkflows(d).map((x) => x.file)).toEqual([".github/workflows/a.yaml", ".github/workflows/b.yml"]);
    expect(detectCronWorkflows(tmp())).toEqual([]);
  });
});

test("sanitizeFindings never leaks secret values", () => {
  const [f] = sanitizeFindings([{ RuleID: "r", File: "a", StartLine: 2, Commit: "abcdef1234567", Secret: "S3CR3T", Match: "M" }]);
  expect(JSON.stringify(f)).not.toContain("S3CR3T"); expect(f).toMatchObject({ rule_id: "r", commit: "abcdef12", full_commit: "abcdef1234567" });
});

describe("security_scanner agent", () => {
  const sent: string[] = [];
  const telegram: any = { sendMessage: async (m: string) => { sent.push(m); return true; } };
  const mk = (scan: (n: string) => any, installed = true) => {
    const gh: any = { getUserRepos: async () => [{ owner: { login: "me" }, full_name: "me/a" }, { owner: { login: "me" }, full_name: "me/b" }], getRepo: async () => ({ default_branch: "main" }), get: async () => ({ author: { login: "dev" } }) };
    const a = new SecurityScannerAgent({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram, targetOwner: "me" });
    a.ensureGitleaksInstalled = async () => installed; a.scanRepository = async (n: string) => scan(n);
    return a;
  };
  test("aggregates findings, cron and errors", async () => {
    const r = await mk((n) => n === "me/a" ? { scanned: true, findings: [{ rule_id: "k", file: "f", line: 1, full_commit: "c1" }], cron_workflows: [{ file: ".github/workflows/x.yml", line: 3, cron: "* * * * *" }] } : { scanned: false, error: "boom" }).run();
    expect(r).toMatchObject({ total_repositories: 2, scanned: 1, failed: 1, total_findings: 1, total_cron_workflows: 1 });
    expect(r.scan_errors).toEqual([{ repository: "me/b", error: "boom" }]);
    expect(sent.join("\n")).toContain("Relatório do Security Scanner");
  });
  test("aborts when gitleaks missing", async () => {
    expect((await mk(() => ({}), false).run()).error).toContain("Failed to install gitleaks");
  });
});
