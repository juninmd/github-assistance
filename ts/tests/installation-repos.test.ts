import { expect, test } from "bun:test";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { GithubClient, GithubError } from "../src/github/client.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";

const missing = join(tmpdir(), "no-such-allowlist.json");

test("allowlist desligada: qualquer owner/repo passa, lista de repos fica vazia", () => {
  const a = new RepositoryAllowlist(missing, false);
  expect(a.isAllowed("me/anything")).toBe(true);
  expect(a.isAllowed("noslash")).toBe(false);
  expect(a.listRepositories()).toEqual([]);
});

test("allowlist ligada continua restritiva", () => {
  expect(new RepositoryAllowlist(missing, true).isAllowed("me/anything")).toBe(false);
});

function client(handler: (path: string) => any[] | Error) {
  const c = new GithubClient("t") as any;
  c.paginate = async (path: string) => { const r = handler(path); if (r instanceof Error) throw r; return r; };
  return c as GithubClient;
}

test("getUserRepos usa /installation/repositories, ordena por updated desc e respeita limit", async () => {
  const seen: string[] = [];
  const c = client((p) => { seen.push(p); return [{ full_name: "a/old", updated_at: "2026-01-01" }, { full_name: "a/new", updated_at: "2026-03-01" }]; });
  const r = await c.getUserRepos({ limit: 1 });
  expect(seen).toEqual(["/installation/repositories"]);
  expect(r.map((x: any) => x.full_name)).toEqual(["a/new"]);
});

test("getUserRepos cai para /user/repos quando o token nao e de instalacao (403)", async () => {
  const seen: string[] = [];
  const c = client((p) => { seen.push(p); return p.startsWith("/installation") ? new GithubError(403, "forbidden") : [{ full_name: "a/b" }]; });
  expect((await c.getUserRepos({ limit: null })).length).toBe(1);
  expect(seen[1]).toStartWith("/user/repos");
});

test("getUserRepos propaga erros que nao sao de autenticacao", async () => {
  const c = client(() => new GithubError(500, "boom"));
  await expect(c.getUserRepos({ limit: null })).rejects.toThrow("boom");
});
