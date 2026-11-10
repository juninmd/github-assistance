// Bootstrap: auth, hash routing with view transitions, and the refresh loop.
import { ApiError, api, token } from "./api.js";
import { promptToken } from "./components/auth.js";
import { icon } from "./dom.js";
import { transition } from "./motion.js";
import { initTheme } from "./theme.js";
import { createFleet } from "./views/fleet.js";
import { createJobs } from "./views/jobs.js";
import { createOverview } from "./views/overview.js";

const VIEWS = ["overview", "jobs", "fleet"];
const $ = (id) => document.getElementById(id);
const live = $("live");
const banner = $("banner");
const interval = $("refresh-interval");
let controller = null;
let timer = null;
let lastSuccess = 0;

const overview = createOverview($("view-overview"), {
  onRange: () => { overview.stale(); refresh(); },
  onStatus: (status) => { jobs.filterBy(status); location.hash = "#jobs"; },
});
const jobs = createJobs($("view-jobs"));
const fleet = createFleet($("view-fleet"));

const currentView = () => (VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview");

function showView() {
  const active = currentView();
  for (const name of VIEWS) $(`view-${name}`).hidden = name !== active;
  for (const tab of document.querySelectorAll(".tab")) {
    if (tab.dataset.view === active) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
}

function paintService(service) {
  const badge = $("mode-badge");
  const autonomous = service.mode === "autonomous";
  badge.hidden = false;
  badge.dataset.tone = service.simulation ? "warning" : autonomous ? "good" : "";
  badge.textContent = service.simulation ? "Simulação" : autonomous ? "Autônomo" : "Observação";
  badge.title = `AUTOMATION_MODE=${service.mode}${service.simulation ? " · SIMULATION_MODE=true" : ""}`;
}

async function load(signal) {
  const view = currentView();
  if (view === "jobs") return jobs.load(signal);
  if (view === "fleet") return fleet.update(await api("/agents", { signal }));
  const data = await api(`/overview?hours=${overview.hours()}`, { signal });
  paintService(data.service);
  overview.update(data);
}

function fail(error) {
  live.dataset.state = "error";
  $("live-text").textContent = "Sem atualização";
  const disabled = error.status === 403;
  banner.hidden = false;
  banner.replaceChildren(icon("info"), disabled
    ? "A API de administração está desativada: defina ADMIN_API_TOKEN no serviço."
    : `Não foi possível atualizar: ${error.message}`);
}

async function refresh() {
  controller?.abort();
  controller = new AbortController();
  live.dataset.busy = "true";
  try {
    await load(controller.signal);
    lastSuccess = Date.now();
    live.dataset.state = "ok";
    banner.hidden = true;
    $("sign-out").hidden = false;
    $("auth-dialog").close();
  } catch (error) {
    if (error.name === "AbortError") return;
    if (error instanceof ApiError && error.status === 401) {
      await promptToken(token.get() ? "Token inválido. Tente novamente." : "");
      return refresh();
    }
    fail(error);
  } finally {
    live.dataset.busy = "false";
    schedule();
  }
}

function schedule() {
  clearTimeout(timer);
  const seconds = Number(interval.value);
  if (seconds > 0) timer = setTimeout(() => (document.hidden ? schedule() : refresh()), seconds * 1000);
}

function tick() {
  if (!lastSuccess || live.dataset.state !== "ok") return;
  const seconds = Math.round((Date.now() - lastSuccess) / 1000);
  $("live-text").textContent = seconds < 5 ? "Atualizado agora" : `Atualizado há ${seconds} s`;
}

initTheme($("theme-toggle"));
$("sign-out").append(icon("logout"));
$("sign-out").addEventListener("click", () => { token.clear(); location.reload(); });
live.addEventListener("click", refresh);
interval.addEventListener("change", schedule);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
window.addEventListener("hashchange", () => transition(() => { showView(); refresh(); }));
setInterval(tick, 1000);
showView();
refresh();
