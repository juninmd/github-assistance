/** GitHub webhook signature check and GitHub App authentication (no JWT dependency). */
import { createHmac, createSign, timingSafeEqual } from "node:crypto";
import { readFileSync } from "node:fs";

const API = "https://api.github.com";

export function validSignature(body: string | Uint8Array, signature: string | null | undefined, secret: string): boolean {
  if (!signature || !signature.startsWith("sha256=")) return false;
  const expected = Buffer.from("sha256=" + createHmac("sha256", secret).update(body).digest("hex"));
  const got = Buffer.from(signature);
  return got.length === expected.length && timingSafeEqual(got, expected);
}

const b64u = (b: Buffer | string) => Buffer.from(b).toString("base64url");

export class GitHubAppAuth {
  private cached: string | null = null;
  private expiresAt = 0;
  constructor(public appId: number, public installationId: number, public privateKeyPath: string) {}

  jwt(): string {
    const now = Math.floor(Date.now() / 1000);
    const key = readFileSync(this.privateKeyPath, "utf8");
    const head = b64u(JSON.stringify({ alg: "RS256", typ: "JWT" }));
    const body = b64u(JSON.stringify({ iat: now - 60, exp: now + 540, iss: String(this.appId) }));
    const sig = createSign("RSA-SHA256").update(`${head}.${body}`).sign(key);
    return `${head}.${body}.${b64u(sig)}`;
  }

  async installationToken(): Promise<string> {
    const now = Date.now() / 1000;
    if (this.cached && now < this.expiresAt - 300) return this.cached;
    const res = await fetch(`${API}/app/installations/${this.installationId}/access_tokens`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.jwt()}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) throw new Error(`installation token request failed (${res.status})`);
    this.cached = String(((await res.json()) as any).token);
    this.expiresAt = now + 3600;
    return this.cached;
  }
}
