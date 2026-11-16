// Admin API client. The token lives in sessionStorage only: per tab, gone on close.
const TOKEN_KEY = "ga.adminToken";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export const token = {
  get() {
    try { return sessionStorage.getItem(TOKEN_KEY) ?? ""; } catch { return this.memory ?? ""; }
  },
  set(value) {
    this.memory = value;
    try { sessionStorage.setItem(TOKEN_KEY, value); } catch { /* storage blocked: keep in memory */ }
  },
  clear() {
    this.memory = "";
    try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* nothing stored */ }
  },
};

export async function api(path, { method = "GET", signal } = {}) {
  let response;
  try {
    response = await fetch(new URL(`../api${path}`, document.baseURI), {
      method,
      signal,
      cache: "no-store",
      headers: { Authorization: `Bearer ${token.get()}` },
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(0, "Sem conexão com o servidor");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail ?? detail; } catch { /* non-JSON error body */ }
    throw new ApiError(response.status, String(detail));
  }
  return response.json();
}

export function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
