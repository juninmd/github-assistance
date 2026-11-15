/** AI clients. All providers are plain HTTP (no SDKs): openai/litellm share the OpenAI-compatible wire format. */
import { HttpError, withRetry } from "../utils/retry.ts";
import { instrument } from "./usage.ts";

export function extractCodeBlock(text: string): string {
  const m = text.match(/```([\s\S]*?)```/);
  if (m) {
    const content = m[1];
    const nl = content.indexOf("\n");
    if (nl >= 0) {
      const first = content.slice(0, nl), rest = content.slice(nl + 1);
      if (/^[A-Za-z0-9]+$/.test(first.trim()) && rest.trim()) return rest.trim() + "\n";
    }
    return content.trim() + "\n";
  }
  return text.trim() + "\n";
}

export function extractJsonObject(text: string): Record<string, any> | null {
  for (const cand of [text.trim(), extractCodeBlock(text).trim()]) {
    if (!cand) continue;
    try { const d = JSON.parse(cand); if (d && typeof d === "object" && !Array.isArray(d)) return d; } catch { /* scan */ }
    for (let i = cand.indexOf("{"); i >= 0; i = cand.indexOf("{", i + 1)) {
      for (let j = cand.lastIndexOf("}"); j > i; j = cand.lastIndexOf("}", j - 1)) {
        try { const d = JSON.parse(cand.slice(i, j + 1)); if (d && typeof d === "object" && !Array.isArray(d)) return d; } catch { /* shrink */ }
      }
    }
  }
  return null;
}

const CONFLICT_PROMPT = (file: string) =>
  "You are an expert software engineer resolving git merge conflicts.\nYour task:\n" +
  "1. Analyze the conflict markers (<<<<<<< HEAD, =======, >>>>>>>) to understand both versions\n" +
  "2. Apply correct logic - prefer the newer implementation unless it breaks functionality\n" +
  "3. Preserve imports, dependencies, and surrounding code\n" +
  `File content:\n${file}\n` +
  "Return ONLY the fully resolved file content with NO conflict markers, NO markdown, NO explanation.";

export abstract class AIClient {
  model = "";
  /** Provider-specific raw text completion. */
  protected abstract complete(prompt: string): Promise<string>;

  generate(prompt: string): Promise<string> { return instrument("generate", this, [prompt], () => this.complete(prompt)); }
  generatePrComment(issue: string): Promise<string> {
    return instrument("generate_pr_comment", this, [issue], () => this.complete(
      "You are a friendly CI assistant. Write a concise GitHub PR comment asking the author to fix the following pipeline issue:\n" + issue));
  }
  resolveConflict(fileContent: string, conflictBlock: string): Promise<string> {
    return instrument("resolve_conflict", this, [fileContent, conflictBlock], async () => extractCodeBlock(await this.complete(CONFLICT_PROMPT(fileContent))));
  }

  async classifySecretFinding(f: Record<string, any>, redactedContext = ""): Promise<{ action: string; reason: string }> {
    const prompt =
      "You are a security reviewer classifying a gitleaks finding.\nDecide using ONLY these actions:\n" +
      "- REMOVE_FROM_HISTORY: real credential or secret material\n" +
      "- IGNORE: placeholder, fake example, fixture, documentation snippet, or uncertain case\n\n" +
      "IMPORTANT: Consider the file name and path when classifying.\nFiles matching these patterns are very likely FALSE POSITIVES (IGNORE):\n" +
      "- Test files (test_*, *_test.*, *_spec.*, *.test.*)\n- Example/sample files (*.example, *.sample, *.template, example_*)\n" +
      "- Documentation (*.md, *.rst, *.txt, docs/*, README*)\n- Lock files (*.lock, package-lock.json, yarn.lock, pnpm-lock.yaml, bun.lock)\n" +
      "- Config templates (.env.example, .env.sample, *.example.*)\n- Fixture/mock data (fixtures/*, mocks/*, __fixtures__/*)\n" +
      "- Generated/vendor files (vendor/*, node_modules/*, dist/*)\n\nIf context is insufficient, choose IGNORE.\nRespond with ONLY valid JSON:\n" +
      '{"action": "REMOVE_FROM_HISTORY", "reason": "short explanation"}\nor\n{"action": "IGNORE", "reason": "short explanation"}\n\n' +
      `Rule: ${f.rule_id ?? "unknown"} - ${f.description ?? ""}\nFile: ${f.file ?? ""}\nLine: ${f.line ?? 0}\nCommit: ${f.commit ?? ""}\nDate: ${f.date ?? ""}\n` +
      `Redacted local context:\n${redactedContext || "Context unavailable."}`;
    try {
      const d = extractJsonObject(await this.generate(prompt));
      const action = String(d?.action ?? "").trim();
      if (!d || !["REMOVE_FROM_HISTORY", "IGNORE"].includes(action)) return { action: "IGNORE", reason: "Could not parse AI response" };
      return { action, reason: String(d.reason ?? "").trim() || "No reason provided by AI" };
    } catch (e: any) { return { action: "IGNORE", reason: `AI analysis failed: ${e?.message ?? e}` }; }
  }

  async analyzePrClosure(persona: string, mission: string, comments: string): Promise<[boolean, string]> {
    const text = await this.generate(
      `Persona: ${persona}\nMissão: ${mission}\n\nAbaixo estão os comentários de um Pull Request. Analise se há uma solicitação clara de fechamento, ` +
      `código ruim ou inseguro, rejeição ou desistência por parte de um autor autorizado.\n\nComentários:\n${comments}\n\n` +
      'Responda EXATAMENTE no formato JSON:\n{"should_close": true, "reason": "motivo sucinto em português"}\nor\n{"should_close": false, "reason": ""}');
    const d = extractJsonObject(text);
    if (d) return [Boolean(d.should_close), String(d.reason ?? "")];
    if (text.toLowerCase().includes("true")) return [true, "Identificado motivo para fechamento (parsing fallback)"];
    return [false, ""];
  }
}

async function postJson(url: string, body: unknown, headers: Record<string, string>, timeoutMs = 300_000): Promise<any> {
  return withRetry(async () => {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) throw new HttpError(res.status, `${url} -> ${res.status}: ${(await res.text()).slice(0, 200)}`);
    return res.json();
  });
}

/** OpenAI-compatible chat completions (OpenAI, and LiteLLM proxy). */
export class OpenAICompatClient extends AIClient {
  constructor(public baseUrl: string, public apiKey: string | null, model: string, private keyEnv = "OPENAI_API_KEY") { super(); this.model = model; }
  protected async complete(prompt: string): Promise<string> {
    if (!this.apiKey && this.keyEnv === "OPENAI_API_KEY") throw new Error("OPENAI_API_KEY is required for OpenAIClient");
    const data = await postJson(`${this.baseUrl}/chat/completions`, { model: this.model, messages: [{ role: "user", content: prompt }] },
      this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {});
    return String(data?.choices?.[0]?.message?.content ?? "").trim();
  }
}

export class OllamaClient extends AIClient {
  constructor(public baseUrl = "http://localhost:11434", model = "llama3", private timeoutMs = ollamaTimeoutMs()) { super(); this.baseUrl = baseUrl.replace(/\/$/, ""); this.model = model; }
  protected async complete(prompt: string): Promise<string> {
    const d = await postJson(`${this.baseUrl}/api/generate`, { model: this.model, prompt, stream: false }, {}, this.timeoutMs);
    return String(d?.response ?? "").trim();
  }
}
export function ollamaTimeoutMs(): number {
  const n = parseInt(process.env.OLLAMA_TIMEOUT_MS ?? "", 10);
  return n > 0 ? n : 300_000;
}

export class GeminiClient extends AIClient {
  constructor(private apiKey: string | null = process.env.GEMINI_API_KEY ?? null, model = "gemini-2.5-flash") { super(); this.model = model; }
  protected async complete(prompt: string): Promise<string> {
    if (!this.apiKey) throw new Error("GEMINI_API_KEY is required for GeminiClient");
    const d = await postJson(`https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent`,
      { contents: [{ parts: [{ text: prompt }] }] }, { "x-goog-api-key": this.apiKey });
    return String(d?.candidates?.[0]?.content?.parts?.map((p: any) => p.text ?? "").join("") ?? "").trim();
  }
}

const normalizeBase = (b: string) => { const n = b.trim().replace(/^["']|["']$/g, "").replace(/\/+$/, ""); return n.endsWith("/v1") ? n : `${n}/v1`; };

export function getAiClient(provider = "ollama", o: { apiKey?: string | null; model?: string; baseUrl?: string | null } = {}): AIClient {
  switch (provider.toLowerCase()) {
    case "gemini": return new GeminiClient(o.apiKey ?? process.env.GEMINI_API_KEY ?? null, o.model ?? "gemini-2.5-flash");
    case "litellm": {
      const key = (o.apiKey ?? process.env.LITELLM_API_KEY ?? "").trim().replace(/^["']|["']$/g, "") || null;
      const base = o.baseUrl ?? process.env.LITELLM_API_BASE;
      if (!base) throw new Error("LITELLM_API_BASE is required for the litellm provider");
      return new OpenAICompatClient(normalizeBase(base), key, o.model ?? process.env.LITELLM_MODEL ?? "cloud/auto", "LITELLM_API_KEY");
    }
    case "ollama": return new OllamaClient(o.baseUrl ?? "http://localhost:11434", o.model ?? "llama3");
    case "openai": return new OpenAICompatClient((o.baseUrl ?? process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1").replace(/\/$/, ""),
      o.apiKey ?? process.env.OPENAI_API_KEY ?? null, o.model ?? "gpt-4o");
    default: throw new Error(`Unknown AI provider: ${provider}`);
  }
}
