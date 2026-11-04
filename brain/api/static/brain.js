// Shared helpers and the app shell (sidebar, banner, topbar), same layout as the demo dashboards.
const api = async (path, opts = {}) => {
  const r = await fetch(path, {headers: {"Content-Type": "application/json"}, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined});
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  return r.json();
};
const post = (path, body) => api(path, {method: "POST", body: body || {}});
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const eur = n => n == null ? "" : "€ " + Math.round(n).toLocaleString("nl-NL");
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const store = {get(k) { try { return localStorage.getItem(k); } catch { return null; } },
               set(k, v) { try { localStorage.setItem(k, v); } catch {} }};
const initials = n => n.split(" ").filter(w => w[0] === w[0].toUpperCase()).map(w => w[0]).slice(0, 2).join("");
const TEAMS = {asia: "Asia", africa: "Africa", americas: "Americas"};
const ICON = {
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>', book: '<path d="M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4z"/>',
  alert: '<path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18h.01"/>', check: '<path d="m5 12 5 5 9-10"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>', gap: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.7M12 17h.01"/>',
};
const icon = n => `<svg class="i" viewBox="0 0 24 24">${ICON[n] || ""}</svg>`;

function toast(msg) {
  let box = $(".toasts"); if (!box) { box = document.createElement("div"); box.className = "toasts"; document.body.append(box); }
  box.innerHTML = `<div class="toast">${esc(msg)}</div>`;
  requestAnimationFrame(() => box.firstChild.classList.add("show"));
  clearTimeout(box._h); box._h = setTimeout(() => box.firstChild && box.firstChild.classList.remove("show"), 2600);
}

function greeting() { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; }
function today() { return new Date().toLocaleDateString("en-GB", {weekday: "long", day: "numeric", month: "long", year: "numeric"}).replace(",", ""); }

// shell({role, nav: [[id, label]], links: [[href, label]], who: html}) builds the page frame; views live in <main id="view">.
function shell({role, nav, links, who, onNav}) {
  document.body.innerHTML = `<div class="app">
    <aside class="sidebar">
      <div class="brand"><span class="brand-name">Company brain</span><span class="label">${esc(role)}</span></div>
      <nav class="nav">${nav.map(([id, l]) => `<button class="nav-btn" data-view="${id}">${esc(l)}<span class="badge" id="badge-${id}" hidden></span></button>`).join("")}</nav>
      <div class="side-links">${links.map(([h, l]) => `<a href="${h}">${esc(l)} →</a>`).join("")}</div>
      <div class="whoami">${who}</div>
    </aside>
    <div class="main">
      <div class="banner">SANDBOX · MADE-UP DATA · NOTHING IS SENT</div>
      <div class="topbar"><span class="label" id="tb-left"></span>
        <div class="tb-right"><span class="tchip"><span class="live"></span><span id="tb-model">model</span></span>
          <span class="pill pill-local" id="tb-ts">TravelSpirit · fake</span><span class="pill pill-concept">Synthetic data</span>
          <a class="tchip" href="/docs" style="text-decoration:none;color:inherit">API</a></div></div>
      <main class="content" id="view"></main>
    </div></div>`;
  $$(".nav-btn").forEach(b => b.onclick = () => go(b.dataset.view));
  function go(id) {
    $$(".nav-btn").forEach(b => { if (b.dataset.view !== id) b.removeAttribute("aria-current"); else b.setAttribute("aria-current", "page"); });
    store.set(role + ":view", id); onNav(id);
  }
  api("/api/status").then(s => {
    $("#tb-model").textContent = `Model: ${s.model}`;
    $("#tb-ts").textContent = `TravelSpirit · ${s.travelspirit} · ${s.travelspirit_write}`;
  });
  return {go, start() { go(store.get(role + ":view") && nav.some(n => n[0] === store.get(role + ":view")) ? store.get(role + ":view") : nav[0][0]); }};
}
function badge(id, n) { const b = $("#badge-" + id); if (!b) return; b.hidden = !n; b.textContent = n; }

const REQ_STATUS = {new: ["New request", "hot"], proposal_draft: ["Draft ready", "hot"], change_requested: ["Change requested", "hot"], proposal_sent: ["Proposal sent", ""],
                    booked: ["Booked", "ok"], lost: ["Lost", ""]};
function sourcesList(sources) {
  const k = (sources || []).filter(s => s.title);
  if (!k.length) return "";
  return `<ul class="src">${k.map((s, i) => `<li><span class="n ${s.outdated ? "old" : ""}">[${i + 1}]</span>
    <div><b>${esc(s.title)}</b><small>Owner ${esc(s.owner)} · review by ${esc(s.review_by)}${s.outdated ? " · past review date, check first" : ""}</small></div></li>`).join("")}</ul>`;
}
