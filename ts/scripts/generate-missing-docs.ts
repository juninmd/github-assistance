#!/usr/bin/env bun
/** One-off: create a missing README.md / AGENTS.md in the owner's repos using a local Ollama model (requires ENABLE_AI=true). */
import { GithubClient, GithubError } from "../src/github/client.ts";

const OLLAMA_URL = process.env.OLLAMA_URL ?? "http://localhost:11434/api/generate", MODEL = process.env.DOCS_MODEL ?? "gemma3:1b";
async function generate(prompt: string): Promise<string> {
  try {
    const res = await fetch(OLLAMA_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: MODEL, prompt, stream: false }), signal: AbortSignal.timeout(180_000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return String(((await res.json()) as any).response ?? "").trim();
  } catch (e) { console.log(`Error communicating with Ollama: ${e}`); return ""; }
}
const readmePrompt = (name: string, desc: string | null, files: string) =>
  `Generate a concise, professional README.md for a repository named '${name}' with the following description: '${desc || "A standard software project."}'.\n` +
  `Here is a list of existing files in the root of the repository to help you understand the project structure:\n${files}\n\n` +
  "Include a short description, an installation section, and a usage section based on the files you see. Only return the raw markdown content, no conversational text.";
const AGENTS_PROMPT = "You are an AI assistant generating guidelines for an AGENTS.md file. The file acts as instructions for AI coding agents working on this repository. " +
  "Generate the guidelines strictly in English. You MUST include the following principles and explicit rules:\n- DRY (Don't Repeat Yourself)\n- KISS (Keep It Simple, Stupid)\n- SOLID principles\n- YAGNI (You Aren't Gonna Need It)\n" +
  "- All development must be productive. Do not use mocks or fake implementations. Use mocks ONLY for tests.\n- Each file must have a maximum of 180 lines of code.\n- Ensure at least 80% test coverage.\n\n" +
  "Return ONLY the raw markdown content without any conversational filler.";

if (!["1", "true", "yes", "on"].includes((process.env.ENABLE_AI ?? "false").toLowerCase())) { console.log("Skipping AI documentation generation (ENABLE_AI is false)."); process.exit(0); }
const token = process.env.GITHUB_TOKEN;
if (!token) { console.log("Error: GITHUB_TOKEN is not set."); process.exit(0); }
const gh = new GithubClient(token), owner = (process.env.GITHUB_OWNER ?? "juninmd").trim().toLowerCase();
const me = await gh.getAuthenticatedLogin();
if (me.trim().toLowerCase() !== owner) { console.log(`Error: authenticated user '${me}' does not match GITHUB_OWNER '${owner}'.`); process.exit(0); }
const repos: any[] = await gh.paginate("/user/repos?affiliation=owner");
for (const repo of repos) {
  if ((repo.owner?.login ?? repo.full_name.split("/")[0]).toLowerCase() !== owner || repo.archived) continue;
  console.log(`Checking repository: ${repo.full_name}`);
  let hasReadme = false;
  try { hasReadme = !!(await gh.getContents(repo.full_name, "README.md")); }
  catch (e) { if (e instanceof GithubError && e.status === 404 && String(e.data?.message ?? "").toLowerCase().includes("empty")) { console.log("  -> Repository is empty, skipping."); continue; } throw e; }
  const create = async (path: string, content: string, message: string) => {
    try { await gh.put(`/repos/${repo.full_name}/contents/${path}`, { message, content: Buffer.from(content, "utf8").toString("base64"), branch: repo.default_branch }); console.log(`  -> Successfully created ${path}`); }
    catch (e) { console.log(`  -> Failed to create ${path}: ${e}`); }
  };
  if (!hasReadme) {
    console.log("  -> README.md is missing. Generating...");
    let files = "No files found.";
    try { files = ((await gh.listContents(repo.full_name, "")) ?? []).map((c: any) => `- ${c.path}`).join("\n") || files; } catch (e) { console.log(`  -> Warning: failed to fetch repository contents: ${e}`); }
    const content = await generate(readmePrompt(repo.name, repo.description, files));
    if (content) await create("README.md", content, "docs: create README.md via AI"); else console.log("  -> Ollama returned empty content for README.md.");
  }
  if (!(await gh.getContents(repo.full_name, "AGENTS.md").catch(() => null))) {
    console.log("  -> AGENTS.md is missing. Generating...");
    const content = await generate(AGENTS_PROMPT);
    if (content) await create("AGENTS.md", content, "docs: create AGENTS.md via AI"); else console.log("  -> Ollama returned empty content for AGENTS.md.");
  }
}
