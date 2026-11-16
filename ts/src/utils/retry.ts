/** Retry with exponential backoff + jitter. */
export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
const RETRYABLE = new Set([429, 500, 502, 503, 504]);
export const isRetryable = (e: unknown): boolean =>
  (e instanceof HttpError && RETRYABLE.has(e.status)) || (e instanceof Error && ["TimeoutError", "AbortError", "TypeError"].includes(e.name));

export async function withRetry<T>(fn: () => Promise<T>, o: { maxAttempts?: number; baseDelay?: number; maxDelay?: number; backoff?: number; retryable?: (e: unknown) => boolean; sleep?: (ms: number) => Promise<void> } = {}): Promise<T> {
  const max = o.maxAttempts ?? 3, maxDelay = o.maxDelay ?? 60, factor = o.backoff ?? 2;
  const sleep = o.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  let delay = o.baseDelay ?? 1;
  for (let attempt = 1; ; attempt++) {
    try { return await fn(); } catch (e) {
      if (attempt >= max || !(o.retryable ?? isRetryable)(e)) throw e;
      await sleep(Math.min(delay + Math.random() * delay * 0.3, maxDelay) * 1000);
      delay = Math.min(delay * factor, maxDelay);
    }
  }
}
