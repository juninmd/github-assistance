/** What an opencode run actually did: skills invoked, tokens, harness version (parsed from `--format json`). */
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { run } from "../../utils/proc.ts";

export const SKILL_TOOLS = new Set(["skill", "skills"]);
export type RunTrace = { harness: string; model: string; skills_used: string[]; skills_available: string[]; tokens_in: number; tokens_out: number; cost: number; structured: boolean; tools: string[] };
export const emptyTrace = (): RunTrace => ({ harness: "opencode", model: "", skills_used: [], skills_available: [], tokens_in: 0, tokens_out: 0, cost: 0, structured: false, tools: [] });

const int = (v: unknown) => { const n = parseInt(String(v), 10); return Number.isNaN(n) ? 0 : n; };
const obj = (v: unknown): Record<string, any> => (v && typeof v === "object" && !Array.isArray(v) ? (v as any) : {});

export function parseEvents(stdout: string): [string, { skills_used: string[]; tools: string[]; tokens_in: number; tokens_out: number; cost: number; structured: boolean }] {
  const texts: string[] = [], skills: string[] = [], tools: string[] = [];
  let tin = 0, tout = 0, cost = 0, structured = false;
  for (const raw of (stdout ?? "").split("\n")) {
    const line = raw.trim();
    if (!line.startsWith("{")) continue;
    let ev: any; try { ev = JSON.parse(line); } catch { continue; }
    if (!ev || typeof ev !== "object" || !("type" in ev)) continue;
    const part = obj(ev.part);
    switch (ev.type) {
      case "text": structured = true; texts.push(String(part.text ?? "")); break;
      case "tool_use": {
        structured = true;
        const tool = String(part.tool ?? ""); tools.push(tool);
        const name = String(obj(obj(part.state).input).name ?? "").trim();
        if (SKILL_TOOLS.has(tool) && name && !skills.includes(name)) skills.push(name);
        break;
      }
      case "step_finish": {
        structured = true;
        const tok = obj(part.tokens); tin += int(tok.input); tout += int(tok.output);
        const c = parseFloat(part.cost ?? 0); if (!Number.isNaN(c)) cost += c;
        break;
      }
      case "step_start": case "reasoning": structured = true; break;
    }
  }
  let text = structured ? texts.filter(Boolean).join("\n").trim() : stdout ?? "";
  if (structured && !text) text = stdout;
  return [text, { skills_used: skills, tools, tokens_in: tin, tokens_out: tout, cost, structured }];
}

export function availableSkills(extraDirs: string[] = []): string[] {
  const roots = [join(homedir(), ".config", "opencode", "skills"), ...extraDirs.flatMap((b) => [join(b, ".opencode", "skills"), join(b, ".agents", "skills")])];
  const names = new Set<string>();
  for (const r of roots) { try { for (const d of readdirSync(r, { withFileTypes: true })) if (existsSync(join(r, d.name, "SKILL.md"))) names.add(d.name); } catch { /* missing */ } }
  return [...names].sort();
}

const versions = new Map<string, string>();
export async function harnessVersion(cmd = ""): Promise<string> {
  cmd ||= Bun.which("opencode") ?? "opencode";
  if (!versions.has(cmd)) {
    const r = await run([cmd, "--version"], { env: { ...process.env, NO_COLOR: "1" }, timeoutMs: 15_000 });
    versions.set(cmd, r.code === 0 ? (r.stdout.trim().split("\n").pop() ?? "").trim() : "");
  }
  return versions.get(cmd)!;
}
export const label = (t?: RunTrace | null) => t?.harness ?? "";
