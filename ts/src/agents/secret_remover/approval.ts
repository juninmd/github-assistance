/**
 * Owner approval for git history rewrites (irreversible): a Telegram button press or an owner `/aprovar` comment on
 * the approval issue. Fail-closed: any error means "not approved". The approval is bound to the exact set of findings.
 */
import { createHash } from "node:crypto";
import type { GithubClient } from "../../github/client.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

type Log = (m: string, level?: string) => void;
export const APPROVAL_LABEL = "secret-guard";
export const APPROVE_RE = /^\s*\/aprovar\b/i;
const CALLBACK_RE = /^sg:([0-9a-f]{10})$/;
const marker = (id: string) => `<!-- secret-guard:${id} -->`;
const telegramMarker = (id: string) => `<!-- secret-guard:approved-telegram:${id} -->`;
const esc = TelegramNotifier.escapeHtml;

export type Finding = Record<string, any>;
export type Approval = { approved: boolean; via: "github" | "telegram" | null; issue: number | null };

const findingKey = (f: Finding) => [f.rule_id ?? f.RuleID ?? "", f.file ?? "", f.line ?? "", f.commit ?? ""].join(":");
/** Same findings -> same id; any new or changed finding needs a new approval. */
export const approvalId = (repo: string, findings: Finding[]) =>
  createHash("sha256").update([repo, ...findings.map(findingKey).sort()].join("\n")).digest("hex").slice(0, 10);

/** Callback ids approved on Telegram since the last poll; only the owner's private chat (or listed user ids) count. */
export class TelegramApprovals {
  constructor(private token: string | null | undefined, private chatId: string | null | undefined, private approverIds: string[], private log: Log, private fetchFn: typeof fetch = fetch) {}

  private api(method: string, params: Record<string, unknown>) {
    return this.fetchFn(`https://api.telegram.org/bot${this.token}/${method}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params), signal: AbortSignal.timeout(20_000) })
      .then((r) => r.json() as Promise<any>);
  }
  authorized(cq: any): boolean {
    if (this.approverIds.length) return this.approverIds.includes(String(cq.from?.id ?? ""));
    return String(cq.message?.chat?.id ?? "") === String(this.chatId) && cq.message?.chat?.type === "private";
  }
  async poll(): Promise<Set<string>> {
    const ids = new Set<string>();
    if (!this.token || !this.chatId) return ids;
    try {
      const res = await this.api("getUpdates", { timeout: 0, allowed_updates: ["callback_query"] });
      if (!res?.ok) { this.log(`Telegram getUpdates refused: ${res?.description ?? "unknown"}`, "WARNING"); return ids; }
      let last = -1;
      for (const u of res.result ?? []) {
        last = Math.max(last, u.update_id);
        const cq = u.callback_query, m = CALLBACK_RE.exec(cq?.data ?? "");
        if (!cq || !m) continue;
        const ok = this.authorized(cq);
        if (ok) ids.add(m[1]);
        await this.api("answerCallbackQuery", { callback_query_id: cq.id, text: ok ? "Aprovado. A remoção roda na próxima execução do secret-guard." : "Sem permissão para aprovar." }).catch(() => {});
      }
      if (last >= 0) await this.api("getUpdates", { offset: last + 1, timeout: 0, limit: 1, allowed_updates: ["callback_query"] });
    } catch (e: any) { this.log(`Telegram approvals unavailable: ${e?.message ?? e}`, "WARNING"); }
    return ids;
  }
}

function issueBody(id: string, findings: Finding[]): string {
  const rows = findings.slice(0, 50).map((f) => `- \`${f.file ?? "?"}\` linha ${f.line ?? 0} · regra \`${f.rule_id ?? f.RuleID ?? "?"}\` · commit \`${String(f.commit ?? "HEAD").slice(0, 8)}\``);
  return [marker(id), "## 🔐 Remoção de segredo do histórico aguardando aprovação", "",
    `O secret-guard classificou ${findings.length} achado(s) como segredo real. Remover reescreve o histórico git do branch padrão (force-push), o que **não tem volta**.`, "",
    ...rows, "",
    "**Para aprovar:** comente `/aprovar` aqui (só o dono do repositório conta) ou toque em **Aprovar** na mensagem do Telegram.",
    "Sem aprovação nada é reescrito. Rotacione o segredo de qualquer forma: removê-lo do histórico não o invalida."].join("\n");
}

export class ApprovalGate {
  constructor(private gh: GithubClient, private telegram: TelegramNotifier, private owner: string, private telegramApproved: Set<string>, private log: Log) {}

  private async openIssues(repo: string): Promise<any[]> {
    return (await this.gh.getOpenIssues(repo, 100)).filter((i) => (i.labels ?? []).some((l: any) => (typeof l === "string" ? l : l.name) === APPROVAL_LABEL));
  }
  private isOwner = (c: any) => (c.user?.login ?? "").toLowerCase() === this.owner.toLowerCase();

  async check(repo: string, id: string): Promise<Approval> {
    try {
      const issue = (await this.openIssues(repo)).find((i) => (i.body ?? "").includes(marker(id)));
      if (this.telegramApproved.has(id)) {
        if (issue) await this.gh.post(`/repos/${repo}/issues/${issue.number}/comments`, { body: `${telegramMarker(id)}\n✅ Aprovado pelo dono via Telegram.` }).catch(() => {});
        return { approved: true, via: "telegram", issue: issue?.number ?? null };
      }
      if (!issue) return { approved: false, via: null, issue: null };
      const comments = await this.gh.getIssueComments(repo, issue.number);
      if (comments.some((c: any) => this.isOwner(c) && APPROVE_RE.test(c.body ?? ""))) return { approved: true, via: "github", issue: issue.number };
      // A Telegram approval persisted by the bot on an earlier run (only a Bot account can author it).
      if (comments.some((c: any) => c.user?.type === "Bot" && (c.body ?? "").includes(telegramMarker(id)))) return { approved: true, via: "telegram", issue: issue.number };
      return { approved: false, via: null, issue: issue.number };
    } catch (e: any) { this.log(`Approval check failed for ${repo}: ${e?.message ?? e}`, "WARNING"); return { approved: false, via: null, issue: null }; }
  }

  /** Open (once per finding set) the approval issue and send the Telegram button. Older requests are superseded. */
  async request(repo: string, id: string, findings: Finding[]): Promise<{ issue: number | null; created: boolean }> {
    try {
      const open = await this.openIssues(repo), existing = open.find((i) => (i.body ?? "").includes(marker(id)));
      if (existing) return { issue: existing.number, created: false };
      const issue = await this.gh.createIssue(repo, { title: "🔐 secret-guard: aprovar remoção de segredo do histórico", body: issueBody(id, findings), labels: [APPROVAL_LABEL] });
      for (const old of open) await this.close(repo, old.number, `Substituída por #${issue.number} (achados mudaram).`);
      await this.telegram.sendMessage(
        `🔐 <b>SECRET GUARD — APROVAÇÃO NECESSÁRIA</b>\n──────────────────────\n📦 <code>${esc(repo)}</code>\n🔥 ${findings.length} segredo(s) real(is) no histórico.\nRemover reescreve o histórico (irreversível). Nada acontece sem sua aprovação.`,
        "HTML", { inline_keyboard: [[{ text: "✅ Aprovar reescrita", callback_data: `sg:${id}` }], [{ text: "🔗 Ver issue", url: issue.html_url }]] });
      return { issue: issue.number, created: true };
    } catch (e: any) { this.log(`Could not request approval for ${repo}: ${e?.message ?? e}`, "WARNING"); return { issue: null, created: false }; }
  }

  async close(repo: string, issue: number, note: string): Promise<void> {
    try {
      await this.gh.post(`/repos/${repo}/issues/${issue}/comments`, { body: note });
      await this.gh.patch(`/repos/${repo}/issues/${issue}`, { state: "closed", state_reason: "completed" });
    } catch (e: any) { this.log(`Could not close approval issue #${issue} in ${repo}: ${e?.message ?? e}`, "WARNING"); }
  }
}
