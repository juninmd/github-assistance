// Token prompt. The dialog cannot be dismissed: without a token there is no data.
import { token } from "../api.js";

const dialog = document.getElementById("auth-dialog");
const form = document.getElementById("auth-form");
const input = document.getElementById("auth-token");
const error = document.getElementById("auth-error");

dialog.addEventListener("cancel", (event) => event.preventDefault());

/** Ask for the admin token; resolves once the user submits one. */
export function promptToken(message = "") {
  error.textContent = message;
  error.hidden = !message;
  input.value = "";
  if (!dialog.open) dialog.showModal();
  input.focus();
  return new Promise((resolve) => {
    form.addEventListener("submit", () => {
      token.set(input.value.trim());
      resolve();
    }, { once: true });
  });
}
