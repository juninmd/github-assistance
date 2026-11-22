/** Telegram notice when a PR conflict needs a human (best-effort). */
import type { TelegramNotifier } from "../../notifications/telegram.ts";
import { card, esc, prButton } from "../../notifications/telegram-format.ts";

type Tg = Pick<TelegramNotifier, "sendMessage">;
export async function sendManualNotice(tg: Tg, pr: any, error: string): Promise<void> {
  const text = card("🚫", "CONFLITO: RESOLUÇÃO MANUAL NECESSÁRIA", pr, ["ℹ️ O PR continua aberto e foi marcado com <code>needs-manual-conflict-resolution</code>.", `<pre>${esc(error.slice(0, 300))}</pre>`]);
  try { await tg.sendMessage(text, "HTML", prButton(pr)); } catch { /* best-effort */ }
}
