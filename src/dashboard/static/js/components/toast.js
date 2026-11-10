import { h } from "../dom.js";

const region = document.getElementById("toasts");

export function toast(message, timeoutMs = 3500) {
  const node = h("div", { class: "toast", text: message });
  region.append(node);
  setTimeout(() => node.remove(), timeoutMs);
}
