/** Redis-backed distributed budget guard for the shared GitHub API token (fail-open). */
import { createHash } from "node:crypto";

export const DEFAULT_BUDGET = 4800, DEFAULT_WINDOW = 3600, DEFAULT_MAX_WAIT = 30;
const DISABLE_COOLDOWN_MS = 60_000;
export class GitHubRateBudgetExhausted extends Error {}

export interface RedisLike {
  incrby(key: string, n: number): Promise<number>;
  expire(key: string, seconds: number): Promise<unknown>;
  ttl(key: string): Promise<number>;
  get(key: string): Promise<string | null>;
  set(key: string, value: string | number): Promise<unknown>;
}

const intEnv = (name: string, d: number, min = 0) => { const n = parseInt(process.env[name] ?? "", 10); return Number.isNaN(n) ? d : Math.max(min, n); };

export class GitHubRateLimiter {
  private key: string;
  private disabledUntil = 0;
  constructor(private client: RedisLike, token: string, public budget = DEFAULT_BUDGET, public window = DEFAULT_WINDOW, public maxWait = DEFAULT_MAX_WAIT, ns = "gha:rl", private sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))) {
    this.key = `${ns}:${createHash("sha256").update(token).digest("hex").slice(0, 12)}`;
  }

  static fromEnv(token: string, client?: RedisLike | null): GitHubRateLimiter | null {
    client ??= redisFromEnv();
    if (!client) return null;
    return new GitHubRateLimiter(client, token, intEnv("GITHUB_RATE_LIMIT_BUDGET", DEFAULT_BUDGET, 1), intEnv("GITHUB_RATE_LIMIT_WINDOW_SECONDS", DEFAULT_WINDOW, 1), intEnv("GITHUB_RATE_LIMIT_MAX_WAIT_SECONDS", DEFAULT_MAX_WAIT));
  }

  async acquire(path = ""): Promise<void> {
    if (path.includes("/rate_limit") || Date.now() < this.disabledUntil) return;
    let ttl: number;
    try {
      const used = await this.client.incrby(this.key, 1);
      if (used === 1) await this.client.expire(this.key, this.window);
      if (used <= this.budget) return;
      ttl = await this.client.ttl(this.key);
    } catch { this.disable(); return; }
    if (ttl > 0 && ttl <= this.maxWait) { await this.sleep(ttl * 1000); return; }
    throw new GitHubRateBudgetExhausted(`GitHub rate budget ${this.budget}/window exhausted; resets in ~${ttl}s`);
  }

  async observe(headers?: Headers | Record<string, string> | null): Promise<void> {
    if (!headers || Date.now() < this.disabledUntil) return;
    const h = (n: string) => (headers instanceof Headers ? headers.get(n) : (headers as any)[n]) ?? null;
    const remaining = h("x-ratelimit-remaining");
    if (remaining === null) return;
    try {
      const limit = parseInt(h("x-ratelimit-limit") ?? String(this.budget), 10);
      const used = Math.max(0, limit - parseInt(remaining, 10));
      const raw = await this.client.get(this.key);
      const raised = used > (raw !== null ? parseInt(raw, 10) : 0);
      if (raised) await this.client.set(this.key, used);
      const reset = h("x-ratelimit-reset");
      // SET clears the key's TTL; restore a window so the counter cannot outlive it.
      if (reset !== null) await this.client.expire(this.key, Math.max(1, parseInt(reset, 10) - Math.floor(Date.now() / 1000)));
      else if (raised) await this.client.expire(this.key, this.window);
    } catch { this.disable(); }
  }
  private disable() { this.disabledUntil = Date.now() + DISABLE_COOLDOWN_MS; }
}

export function redisFromEnv(): RedisLike | null {
  const url = process.env.REDIS_URL, host = process.env.REDIS_HOST;
  if (!url && !host) return null;
  try {
    const target = url ?? `redis://${process.env.REDIS_PASSWORD ? `:${encodeURIComponent(process.env.REDIS_PASSWORD)}@` : ""}${host}:${intEnv("REDIS_PORT", 6379, 1)}/${intEnv("REDIS_DB", 0)}`;
    const c = new Bun.RedisClient(target, { connectionTimeout: 500, idleTimeout: 0 } as any);
    return {
      incrby: async (k, n) => Number(await c.send("INCRBY", [k, String(n)])),
      expire: (k, s) => c.expire(k, s),
      ttl: async (k) => Number(await c.ttl(k)),
      get: (k) => c.get(k),
      set: (k, v) => c.set(k, String(v)),
    };
  } catch { return null; }
}
