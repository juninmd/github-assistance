/** Counting semaphore with timed acquire (threading.Semaphore equivalent). */
export class Semaphore {
  private waiters: ((ok: boolean) => void)[] = [];
  constructor(private permits: number) {}
  acquire(timeoutMs = Infinity): Promise<boolean> {
    if (this.permits > 0) { this.permits--; return Promise.resolve(true); }
    return new Promise((resolve) => {
      const waiter = (ok: boolean) => { clearTimeout(timer); resolve(ok); };
      const timer = Number.isFinite(timeoutMs) ? setTimeout(() => { this.waiters = this.waiters.filter((w) => w !== waiter); resolve(false); }, timeoutMs) : undefined;
      this.waiters.push(waiter);
    });
  }
  release(): void { const next = this.waiters.shift(); if (next) next(true); else this.permits++; }
}
