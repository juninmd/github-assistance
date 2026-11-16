/** Telegram notifications (HTML parse mode, auto-split, retry). */
import { HttpError, withRetry } from "../utils/retry.ts";
import { getLogger } from "../utils/logger.ts";

const log = getLogger("telegram");
const MD_ESCAPE = /[\\_*[\]()~`>#+\-=|{}.!]/g;

export class TelegramNotifier {
  static MAX_LENGTH = 4096;
  constructor(public botToken?: string | null, public chatId?: string | null, public prefix?: string | null) {}
  get enabled() { return !!(this.botToken && this.chatId); }
  static escape = (t?: string | null) => (t ? t.replace(MD_ESCAPE, (c) => `\\${c}`) : "");
  static escapeHtml = (t?: string | null) => (t ? t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") : "");

  async sendMessage(text: string, parseMode = "HTML", replyMarkup?: object): Promise<boolean> {
    if (!this.enabled) return false;
    if (!String(this.chatId).trim()) { log.warning("Telegram chat_id is empty, skipping notification"); return false; }
    if (this.prefix && !text.includes(`<b>${this.prefix}</b>`)) text = `<b>${this.prefix}</b>\n` + text;
    const parts = this.split(text);
    let ok = true;
    for (let i = 0; i < parts.length; i++) ok = (await this.post(parts[i], parseMode, i === parts.length - 1 ? replyMarkup : undefined)) && ok;
    return ok;
  }

  private async post(text: string, parseMode: string, replyMarkup?: object): Promise<boolean> {
    const payload: Record<string, unknown> = { chat_id: this.chatId, text, parse_mode: parseMode, disable_web_page_preview: false };
    if (replyMarkup) payload.reply_markup = replyMarkup;
    try {
      return await withRetry(async () => {
        const res = await fetch(`https://api.telegram.org/bot${this.botToken}/sendMessage`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal: AbortSignal.timeout(30_000) });
        if (res.ok) return true;
        const body = await res.text();
        if (parseMode && res.status === 400 && body.includes("can't parse entities")) return this.post(text, "", replyMarkup);
        if ([429, 500, 502, 503, 504].includes(res.status)) throw new HttpError(res.status, "telegram");
        log.warning(`Telegram HTTP ${res.status}: send failed`);
        return false;
      }, { baseDelay: 2 });
    } catch { log.warning("Telegram send failed"); return false; }
  }

  async sendPrNotification(pr: any): Promise<void> {
    const e = TelegramNotifier.escapeHtml;
    let body = pr.body || "Sem descrição.";
    if (body.length > 300) body = body.slice(0, 297) + "...";
    const text = `🐙 <b>GITHUB ASSISTANCE</b>\n──────────────────────\n🎊 <b>PULL REQUEST MERGEADO!</b>\n\n🏢 <b>Repositório:</b> <code>${e(pr.base.repo.full_name)}</code>\n` +
      `🆔 <b>PR:</b> <code>#${pr.number}</code>\n📌 <b>Título:</b> <b>${e(pr.title)}</b>\n👤 <b>Autor:</b> <code>${e(pr.user.login)}</code>\n\n📖 <b>Descrição:</b>\n<i>${e(body)}</i>\n──────────────────────`;
    await this.sendMessage(text, "HTML", { inline_keyboard: [[{ text: "🔗 Ver PR no GitHub", url: pr.html_url }]] });
  }

  split(text: string): string[] {
    const max = TelegramNotifier.MAX_LENGTH;
    if (text.length <= max) return [text];
    const parts: string[] = [];
    let rest = text;
    while (rest) {
      if (rest.length <= max - 50) { parts.push(rest); break; }
      let cut = rest.lastIndexOf("\n", max - 50);
      if (cut === -1) cut = max - 50;
      parts.push(rest.slice(0, cut).trimEnd());
      rest = rest.slice(cut).trimStart();
    }
    return parts.length > 1 ? parts.map((p, i) => `${p}\n\n<i>(parte ${i + 1}/${parts.length})</i>`) : parts;
  }
}
