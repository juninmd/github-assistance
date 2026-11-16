/** In-memory failed-auth throttle for the admin API (brute-force guard). */
export class AuthThrottle {
  private failures = new Map<string, number[]>();
  constructor(private maxFailures = 10, private window = 60, private clock = () => performance.now() / 1000) {}
  private prune(c: string, now: number): number[] {
    const hits = (this.failures.get(c) ?? []).filter((t) => now - t <= this.window);
    hits.length ? this.failures.set(c, hits) : this.failures.delete(c);
    return hits;
  }
  retryAfter(c: string): number {
    const now = this.clock();
    const hits = this.prune(c, now);
    return hits.length < this.maxFailures ? 0 : Math.max(1, Math.floor(hits[0] + this.window - now) + 1);
  }
  recordFailure(c: string) { this.failures.set(c, [...(this.failures.get(c) ?? []), this.clock()]); }
  reset(c: string) { this.failures.delete(c); }
}
