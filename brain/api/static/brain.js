// Shared helpers and the app shell (sidebar, banner, topbar), same layout as the demo dashboards.
// Sign-in. Sandbox: the person picked on the sign-in screen. Pilot and live: Microsoft (Entra ID) through
// MSAL, the access token goes with every request and the API checks it and its app roles.
let AUTH = null, MSAL = null, TOKEN = null;
const authReady = (async () => {
  try { AUTH = await (await fetch("/api/auth-config")).json(); } catch { AUTH = {mode: "sandbox"}; }
  if (AUTH.mode !== "entra" || !AUTH.client_id) return;
  await new Promise((ok, fail) => { const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/@azure/msal-browser@3.27.0/lib/msal-browser.min.js"; s.onload = ok; s.onerror = fail; document.head.append(s); });
  MSAL = new msal.PublicClientApplication({auth: {clientId: AUTH.client_id, authority: `https://login.microsoftonline.com/${AUTH.tenant_id}`,
    redirectUri: location.origin + "/static/index.html"}, cache: {cacheLocation: "sessionStorage"}});
  await MSAL.initialize();
  const res = await MSAL.handleRedirectPromise();
  const account = (res && res.account) || MSAL.getAllAccounts()[0];
  if (!account) { await MSAL.loginRedirect({scopes: [AUTH.api_scope]}); return; }
  TOKEN = (await MSAL.acquireTokenSilent({account, scopes: [AUTH.api_scope]}).catch(() => MSAL.acquireTokenRedirect({scopes: [AUTH.api_scope]}))).accessToken;
})();

const api = async (path, opts = {}) => {
  await authReady;
  const headers = {"Content-Type": "application/json"};
  const who = store.get("me");
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  else if (who) headers["X-Brain-User"] = who;
  const r = await fetch(path, {headers, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined});
  if (r.status === 401 && !location.pathname.endsWith("index.html")) {
    location.href = "/static/index.html?next=" + encodeURIComponent(location.pathname.split("/").pop());
    throw new Error("Sign in first");
  }
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  const type = r.headers.get("content-type") || "";
  return type.includes("json") ? r.json() : r.text();
};
const post = async (path, body) => {
  const r = await api(path, {method: "POST", body: body || {}});
  if (r && r.ask_autosend) askAutoSend(r.ask_autosend);
  return r;
};
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const eur = n => n == null ? "" : "€ " + Math.round(n).toLocaleString("nl-NL");
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const store = {get(k) { try { return localStorage.getItem(k) || sessionMem[k] || null; } catch { return sessionMem[k] || null; } },
               set(k, v) { sessionMem[k] = v; try { localStorage.setItem(k, v); } catch {} }};
const sessionMem = {};
let ME = null;
async function loadMe() { ME = await api("/api/me"); return ME; }
const SCREENS = [["specialist.html", "Specialist view", "drafts.approve_customer"], ["teamlead.html", "Team lead view", "team.metrics"],
                 ["backoffice.html", "Back office view", "backoffice.board"], ["maintenance.html", "Maintenance", "maintenance"],
                 ["users.html", "User management", "users.manage"]];
const ROLE_LABEL = {specialist: "specialist", back_office: "back office", team_lead: "team lead", content: "product and content", admin: "admin"};
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
function today() { return new Date().toLocaleDateString(LANG === "nl" ? "nl-NL" : "en-GB", {weekday: "long", day: "numeric", month: "long", year: "numeric"}).replace(",", ""); }

// shell({role, nav: [[id, label]], links: [[href, label]], who: html}) builds the page frame; views live in <main id="view">.
const ROLE_KEY = {"Specialist dashboard": "specialist", "Back office": "back_office", "Team lead": "team_lead", "Maintenance": "maintenance", "User management": "maintenance"};
function shell({role, nav, links, who, onNav, needs}) {
  links = links || [];
  document.body.dataset.role = ROLE_KEY[role] || "other";
  document.title = `${T(role)} · ${T("Company brain")}`;
  document.body.innerHTML = `<div class="app">
    <aside class="sidebar">
      <div class="brand"><span class="brand-name">Company brain</span><span class="label">${esc(role)}</span></div>
      <nav class="nav">${nav.map(([id, l]) => `<button class="nav-btn" data-view="${id}">${esc(l)}<span class="badge" id="badge-${id}" hidden></span></button>`).join("")}</nav>
      <div class="side-links" id="side-links"></div>
      <div class="whoami" id="whoami">${who || ""}</div>
    </aside>
    <div class="main">
      <div class="banner">SANDBOX · MADE-UP DATA · NOTHING IS SENT</div>
      <div class="topbar"><span class="label" id="tb-left"></span>
        <div class="tb-right"><span class="tchip"><span class="live"></span><span id="tb-model">model</span></span>
          <span class="pill pill-local" id="tb-ts">TravelSpirit · fake</span><span class="pill pill-concept">Synthetic data</span>
          <a class="tchip" href="/docs" style="text-decoration:none;color:inherit">API</a>
          <span class="langs" role="group" aria-label="Language"><button class="lang" data-lang="en" aria-pressed="${LANG === "en"}">EN</button><button class="lang" data-lang="nl" aria-pressed="${LANG === "nl"}">NL</button></span></div></div>
      <main class="content" id="view"></main>
    </div></div>`;
  $$(".nav-btn").forEach(b => b.onclick = () => go(b.dataset.view));
  $$(".lang").forEach(b => b.onclick = () => b.dataset.lang !== LANG && setLang(b.dataset.lang));
  function go(id) {
    $$(".nav-btn").forEach(b => { if (b.dataset.view !== id) b.removeAttribute("aria-current"); else b.setAttribute("aria-current", "page"); });
    store.set(role + ":view", id); onNav(id);
  }
  api("/api/status").then(s => {
    $("#tb-model").textContent = `Model: ${s.model}`;
    $("#tb-ts").textContent = `TravelSpirit · ${s.travelspirit} · ${s.travelspirit_write}`;
  });
  const ready = loadMe().then(me => {
    const here = location.pathname.split("/").pop();
    $("#side-links").innerHTML = SCREENS.filter(([h, , p]) => h !== here && me.can.includes(p)).map(([h, l]) => `<a href="${h}">${esc(l)} →</a>`).join("");
    if (!who) $("#whoami").innerHTML = `<span class="avatar">${esc(initials(me.name))}</span><div>${esc(me.name)}<small>${esc(me.roles.map(r => T(ROLE_LABEL[r] || r)).join(", "))} · <a href="index.html" style="color:inherit">switch</a></small></div>`;
    if (needs && !me.can.includes(needs)) {
      $("#view").innerHTML = `<div class="detail empty"><b>Not for your role</b>${esc(me.name)} (${esc(me.roles.map(r => T(ROLE_LABEL[r] || r)).join(", "))}) cannot open this screen. <a href="index.html">Sign in as someone else</a>.</div>`;
      throw new Error("forbidden");
    }
    autoSendWatch();
    return me;
  });
  return {go, ready, start() { ready.then(() => go(store.get(role + ":view") && nav.some(n => n[0] === store.get(role + ":view")) ? store.get(role + ":view") : nav[0][0])).catch(() => {}); }};
}
function badge(id, n) { const b = $("#badge-" + id); if (!b) return; b.hidden = !n; b.textContent = n; }

const PR_STATUS = {to_send: "To send", waiting: "Waiting for reply", chased: "Reminder sent", answered: "Answered", declined: "Not available", unclear: "Needs reading"};
const prStatus = s => PR_STATUS[s] || String(s || "").replace("_", " ");
const REQ_STATUS = {new: ["New request", "hot"], proposal_draft: ["Draft ready", "hot"], change_requested: ["Change requested", "hot"], proposal_sent: ["Proposal sent", ""],
                    booked: ["Booked", "ok"], lost: ["Lost", ""]};
function sourcesList(sources) {
  const k = (sources || []).filter(s => s.title);
  if (!k.length) return "";
  return `<ul class="src">${k.map((s, i) => `<li><span class="n ${s.outdated ? "old" : ""}">[${i + 1}]</span>
    <div><b>${esc(s.title)}</b><small>Owner ${esc(s.owner)} · review by ${esc(s.review_by)}${s.outdated ? " · past review date, check first" : ""}</small></div></li>`).join("")}</ul>`;
}

async function copyText(id) {
  const el = document.getElementById(id);
  const text = el.value !== undefined ? el.value : el.textContent;
  try { await navigator.clipboard.writeText(text); toast("Copied. Paste it into TravelSpirit."); }
  catch { el.select && el.select(); toast("Select and copy the text"); }
}

async function openFile(path) {
  await authReady;
  const r = await fetch(path, {headers: TOKEN ? {"Authorization": "Bearer " + TOKEN} : {"X-Brain-User": store.get("me") || ""}});
  if (!r.ok) { toast("Cannot open this file"); return; }
  const url = URL.createObjectURL(await r.blob());
  window.open(url, "_blank");
}
const fileUrl = p => "/api/files/" + p.split("/").slice(-2).join("/");
function extraBlocks(d) {
  const x = d.data || {};
  if (d.kind === "alternatives") return `<p class="label sect">Versions</p><div class="concept"><table class="itin">
    <tr><td><b>Current proposal</b></td><td></td><td class="num">${eur(x.current_sell_eur)}</td></tr>
    ${x.versions.map(v => `<tr><td><b>${esc(v.label)}</b></td><td>${esc(v.route.map(r => `${r.stop} (${r.nights})`).join(", "))}<br><span style="color:var(--muted)">${esc(v.route.map(r => r.hotel).join(", "))}</span></td><td class="num">${eur(v.price.sell_eur)}</td></tr>`).join("")}</table></div>`;
  if (d.kind === "extras") return `<p class="label sect">Suggested extras</p><div class="concept"><table class="itin">${x.extras.map(e =>
    `<tr><td><b>${esc(e.name)}</b></td><td>${esc(e.stop)}</td><td class="num">${eur(e.price_eur)}</td></tr>`).join("") || `<tr><td>Nothing that fits yet</td></tr>`}</table></div>`;
  if (d.kind === "complaint_reply") return `<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr));margin:18px 0 0">
    <div class="kpi ${x.severity === "high" ? "hot" : ""}"><span class="label">Severity</span><b>${esc(x.severity)}</b><p class="sub">${x.while_travelling ? "travelling now" : "not travelling"}</p></div>
    <div class="kpi"><span class="label">About</span><b style="font-size:18px">${esc(x.topics.join(", "))}</b></div>
    <div class="kpi"><span class="label">Internal actions</span><p class="sub" style="color:var(--ink)">${esc(x.actions.join("; "))}</p></div></div>`;
  if (d.kind === "roadbook") return `<p class="label sect">Documents</p><div class="chips"><button class="pchip sea" onclick="openFile('${fileUrl(x.roadbook)}')">Roadbook (PDF)</button>
    ${x.vouchers.map(v => `<button class="pchip" onclick="openFile('${fileUrl(v.path)}')">Voucher ${esc(v.partner)}</button>`).join("")}</div>`;
  if (d.kind === "next_trip") return `<p class="label sect">Suggestions</p><div class="chips">${x.suggestions.map(o => `<span class="pchip sea">${esc(o.name)}</span>`).join("")}</div>`;
  return "";
}

// Automatic send: the question after ten unchanged approvals, and the countdown with a Stop button.
let AUTO = {switches: [], counting: [], hold_seconds: 10}, autoTimer = null, autoAsked = new Set();
function askAutoSend(q) {
  if (autoAsked.has(q.kind)) return; autoAsked.add(q.kind);
  const box = document.createElement("div");
  box.className = "autoask"; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", "Automatic send");
  box.innerHTML = `<b>Send automatically from now on?</b><p>${esc(q.text)}</p>
    <div class="row-btns"><button class="btn btn-primary btn-sm" data-a="yes">Yes, send automatically</button><button class="btn btn-outline btn-sm" data-a="no">No, keep asking</button></div>`;
  document.body.append(box);
  box.querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
    await post(`/api/autosend/${q.kind}`, {choice: b.dataset.a}); box.remove();
    toast(b.dataset.a === "yes" ? `Automatic send on for ${q.label}` : "Fine, you keep approving them");
    autoSendWatch();
  });
}
async function autoSendWatch() {
  clearTimeout(autoTimer);
  try { AUTO = await api("/api/autosend"); } catch { return; }
  AUTO.fetched = Date.now();
  AUTO.switches.filter(x => x.ask).forEach(x => askAutoSend(x.ask));
  renderAuto();
  if (AUTO.switches.some(x => x.status === "on")) autoTimer = setTimeout(autoSendWatch, document.hidden ? 15000 : 3000);
}
const autoFired = new Set();
function renderAuto() {
  let box = $(".autosend");
  const on = AUTO.switches.filter(x => x.status === "on");
  if (!on.length && !AUTO.counting.length) { box && box.remove(); return; }
  if (!box) { box = document.createElement("div"); box.className = "autosend"; box.setAttribute("aria-live", "polite"); document.body.append(box); }
  const left = c => Math.max(0, Math.ceil(c.seconds_left - (Date.now() - AUTO.fetched) / 1000));
  box.innerHTML = AUTO.counting.map(c => `<div class="acount"><span class="secs">${left(c)}</span>
      <div><small>Sends in ${left(c)} s</small><b>${esc(c.title)}</b></div><button class="btn btn-dark btn-sm" data-stop="${c.id}">Stop</button></div>`).join("")
    + `<div class="aon">Automatic send: ${on.map(x => `${esc(T(x.label))} <button class="btn-link" data-off="${x.kind}">Switch off</button>`).join(" · ")}</div>`;
  box.querySelectorAll("[data-stop]").forEach(b => b.onclick = async () => {
    await post(`/api/drafts/${b.dataset.stop}/stop`); toast("Stopped. It waits for you."); autoSendWatch(); });
  box.querySelectorAll("[data-off]").forEach(b => b.onclick = async () => {
    await post(`/api/autosend/${b.dataset.off}`, {choice: "off"}); toast("Automatic send switched off"); autoSendWatch(); });
  AUTO.counting.filter(c => left(c) === 0 && !autoFired.has(c.id)).forEach(async c => {
    autoFired.add(c.id);
    try { const r = await post(`/api/drafts/${c.id}/send-due`); toast(r.sent ? "Sent automatically" : "Not sent: " + (r.blocked || "it waits for you")); } catch {}
    autoSendWatch();
  });
  if (AUTO.counting.length) requestAnimationFrame(() => setTimeout(renderAuto, 250));
}
