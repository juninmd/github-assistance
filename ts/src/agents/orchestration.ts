/** Agent orchestration: dependency/priority ordering and parallel batches. Cycles and missing deps fail loudly. */
import { AGENT_CATALOG, AgentPriority } from "./catalog.ts";

export class AgentOrchestrator {
  deps = new Map<string, string[]>();
  priorities = new Map<string, AgentPriority>();
  register(name: string, priority = AgentPriority.MEDIUM, dependsOn: string[] = []) { this.deps.set(name, dependsOn); this.priorities.set(name, priority); }
  private depsOf = (a: string) => this.deps.get(a) ?? [];
  private canRun = (a: string, done: Set<string>) => this.depsOf(a).every((d) => done.has(d));
  private prio = (a: string) => this.priorities.get(a) ?? AgentPriority.MEDIUM;

  validate(agents: string[]): void {
    const missing = new Set(agents.flatMap((a) => this.depsOf(a)).filter((d) => !this.deps.has(d)));
    if (missing.size) throw new Error(`missing dependencies: ${[...missing].sort().join(", ")} are not registered`);
    this.order(agents);
  }
  /** True when every unmet dependency of the remaining agents is outside the set (not a cycle). */
  private externalOnly(remaining: Set<string>) { return [...remaining].every((a) => !this.depsOf(a).some((d) => remaining.has(d))); }

  order(agents: string[]): string[] {
    const done = new Set<string>(), out: string[] = [], remaining = new Set(agents);
    while (remaining.size) {
      const ready = [...remaining].filter((a) => this.canRun(a, done)).sort((a, b) => this.prio(a) - this.prio(b));
      if (!ready.length) {
        if (this.externalOnly(remaining)) { out.push(...[...remaining].sort()); break; }
        throw new Error(`circular dependency detected among: ${JSON.stringify([...remaining].sort())}`);
      }
      out.push(ready[0]); done.add(ready[0]); remaining.delete(ready[0]);
    }
    return out;
  }
  executionOrder(agents: string[]) { this.validateMissing(agents); return this.order(agents); }
  private validateMissing(agents: string[]) {
    const missing = new Set(agents.flatMap((a) => this.depsOf(a)).filter((d) => !this.deps.has(d)));
    if (missing.size) throw new Error(`missing dependencies: ${[...missing].sort().join(", ")} are not registered`);
  }

  parallelBatches(agents: string[]): string[][] {
    this.validate(agents);
    const done = new Set<string>(), batches: string[][] = [], remaining = new Set(agents);
    while (remaining.size) {
      const ready = agents.filter((a) => remaining.has(a) && this.canRun(a, done));
      if (!ready.length) {
        if (this.externalOnly(remaining)) { batches.push([...remaining].sort()); break; }
        throw new Error(`circular dependency detected among: ${JSON.stringify([...remaining].sort())}`);
      }
      batches.push(ready);
      ready.forEach((a) => { done.add(a); remaining.delete(a); });
    }
    return batches;
  }
}

export function createDefaultOrchestrator(): AgentOrchestrator {
  const o = new AgentOrchestrator();
  for (const s of AGENT_CATALOG) o.register(s.name, s.priority, s.dependsOn);
  return o;
}
