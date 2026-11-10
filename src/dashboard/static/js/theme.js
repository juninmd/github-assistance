import { icon } from "./dom.js";

const KEY = "ga.theme";
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function stored() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

function current() {
  return document.documentElement.dataset.theme ?? (systemDark.matches ? "dark" : "light");
}

export function initTheme(button) {
  const saved = stored();
  if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  const paint = () => {
    const dark = current() === "dark";
    button.replaceChildren(icon(dark ? "sun" : "moon"));
    button.setAttribute("aria-label", dark ? "Usar tema claro" : "Usar tema escuro");
    button.title = button.getAttribute("aria-label");
  };
  button.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch { /* preference stays for this page only */ }
    paint();
  });
  systemDark.addEventListener("change", paint);
  paint();
}
