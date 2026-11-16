/** Job prioritization by repo/label/title patterns (config/priorities.json). */
import { readFileSync } from "node:fs";

type Rule = [RegExp, number];
const rules = (xs: any): Rule[] => (Array.isArray(xs) ? xs : []).map((r) => [new RegExp(r.pattern ?? ""), Number(r.priority ?? 0)]);

export class Priorities {
  private repos: Rule[] = []; private labels: Rule[] = []; private titles: Rule[] = [];
  constructor(public path = "config/priorities.json") {
    let d: any = {};
    try { d = JSON.parse(readFileSync(path, "utf8")); } catch { /* defaults */ }
    this.repos = rules(d.repositories); this.labels = rules(d.labels); this.titles = rules(d.titles);
  }
  priorityFor(prRef: string, o: { labels?: string[]; title?: string } = {}): number {
    const repo = prRef.split("#", 1)[0];
    let p = 0;
    for (const [re, v] of this.repos) if (re.test(repo)) p += v;
    for (const l of o.labels ?? []) for (const [re, v] of this.labels) if (re.test(l)) p += v;
    for (const [re, v] of this.titles) if (re.test(o.title ?? "")) p += v;
    return p;
  }
}
