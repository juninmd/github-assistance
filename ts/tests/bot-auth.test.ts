import { afterEach, expect, test } from "bun:test";
import { generateKeyPairSync } from "node:crypto";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { botAuthActive, initBotAuth, liveBotToken, stopBotAuth } from "../src/github/bot-auth.ts";

const realFetch = globalThis.fetch;
afterEach(() => { stopBotAuth(); globalThis.fetch = realFetch; });

function key() {
  const f = join(mkdtempSync(join(tmpdir(), "ba-")), "k.pem");
  writeFileSync(f, generateKeyPairSync("rsa", { modulusLength: 2048 }).privateKey.export({ type: "pkcs8", format: "pem" }));
  return f;
}

test("app token wins over PAT and PAT is dropped from env", async () => {
  globalThis.fetch = (async () => new Response(JSON.stringify({ token: "ghs_app" }), { status: 201 })) as any;
  const env: Record<string, string | undefined> = { GITHUB_TOKEN: "ghp_pat", GH_PAT: "ghp_pat2" };
  expect(await initBotAuth(env, 1, 2, key())).toBe("ghs_app");
  expect([env.GITHUB_TOKEN, env.GH_PAT, liveBotToken(), botAuthActive()]).toEqual(["ghs_app", undefined, "ghs_app", true]);
});

test("no app config keeps the PAT path; partial config throws instead of falling back", async () => {
  expect(await initBotAuth({}, null, null, null)).toBeNull();
  expect(botAuthActive()).toBe(false);
  expect(initBotAuth({ GITHUB_TOKEN: "ghp_pat" }, 1, null, null)).rejects.toThrow("incomplete");
});

test("token request failure throws and never falls back to PAT", async () => {
  globalThis.fetch = (async () => new Response("no", { status: 401 })) as any;
  expect(initBotAuth({ GITHUB_TOKEN: "ghp_pat" }, 1, 2, key())).rejects.toThrow("installation token");
});
