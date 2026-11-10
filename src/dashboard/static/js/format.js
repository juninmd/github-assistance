const LOCALE = "pt-BR";
const integer = new Intl.NumberFormat(LOCALE);
const compactFormat = new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 });
const percentFormat = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 1 });
const dateTimeFormat = new Intl.DateTimeFormat(LOCALE, { dateStyle: "short", timeStyle: "medium" });
const hourFormat = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit" });
const dayHourFormat = new Intl.DateTimeFormat(LOCALE, { weekday: "short", hour: "2-digit" });
const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto", style: "short" });

export const num = (value) => integer.format(value ?? 0);
export const compact = (value) => (Math.abs(value ?? 0) < 10000 ? num(value) : compactFormat.format(value));
export const percent = (ratio) => (ratio == null ? "—" : percentFormat.format(ratio));
export const dateTime = (seconds) => (seconds ? dateTimeFormat.format(new Date(seconds * 1000)) : "—");

export function duration(seconds) {
  if (!seconds || seconds < 1) return "agora";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min`;
  return `${Math.floor(seconds / 86400)} d ${Math.round((seconds % 86400) / 3600)} h`;
}

export function ago(seconds, now = Date.now() / 1000) {
  if (!seconds) return "—";
  const delta = seconds - now;
  const abs = Math.abs(delta);
  if (abs < 45) return "agora";
  if (abs < 3600) return relative.format(Math.round(delta / 60), "minute");
  if (abs < 86400) return relative.format(Math.round(delta / 3600), "hour");
  return relative.format(Math.round(delta / 86400), "day");
}

const hour = (date) => `${hourFormat.format(date).replace(/\D/g, "")}h`;

/** Axis label for a bucket start; multi-day windows include the weekday. */
export function bucketLabel(seconds, stepSeconds) {
  const date = new Date(seconds * 1000);
  return stepSeconds > 3600 ? dayHourFormat.format(date) : hour(date);
}

export function bucketRange(seconds, stepSeconds) {
  const start = new Date(seconds * 1000);
  const from = stepSeconds > 3600 ? dayHourFormat.format(start) : hour(start);
  return `${from} – ${hour(new Date((seconds + stepSeconds) * 1000))}`;
}
