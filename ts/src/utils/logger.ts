/** Structured logger with correlation id (same line format as the Python version). */
import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";

const storage = new AsyncLocalStorage<{ cid: string }>();
let currentCid = "";

export function newCorrelationId(): string {
  currentCid = randomUUID().replace(/-/g, "").slice(0, 8);
  return currentCid;
}
export function getCorrelationId(): string {
  return storage.getStore()?.cid ?? currentCid;
}

const LEVELS: Record<string, number> = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 };

export class StructuredLogger {
  private min: number;
  constructor(public name: string, minLevel = process.env.LOG_LEVEL ?? "INFO") {
    this.min = LEVELS[minLevel.toUpperCase()] ?? 20;
  }
  private emit(level: string, msg: string, extra?: Record<string, unknown>): void {
    if ((LEVELS[level] ?? 0) < this.min) return;
    const now = new Date().toISOString().slice(0, 19);
    const parts = [`[${now}]`, `[${level}]`, `[${this.name}]`];
    const cid = getCorrelationId();
    if (cid) parts.push(`[cid:${cid}]`);
    parts.push(msg);
    if (extra && Object.keys(extra).length) {
      parts.push("| " + Object.entries(extra).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" "));
    }
    const line = parts.join(" ");
    if (level === "ERROR" || level === "CRITICAL") console.error(line);
    else console.log(line);
  }
  debug(m: string, e?: Record<string, unknown>) { this.emit("DEBUG", m, e); }
  info(m: string, e?: Record<string, unknown>) { this.emit("INFO", m, e); }
  warning(m: string, e?: Record<string, unknown>) { this.emit("WARNING", m, e); }
  error(m: string, e?: Record<string, unknown>) { this.emit("ERROR", m, e); }
  critical(m: string, e?: Record<string, unknown>) { this.emit("CRITICAL", m, e); }
}

export const getLogger = (name: string) => new StructuredLogger(name);
