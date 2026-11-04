// Shared helpers for the sandbox screens.
const api = async (path, opts = {}) => {
  const r = await fetch(path, {headers: {"Content-Type": "application/json"}, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined});
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  return r.json();
};
const post = (path, body) => api(path, {method: "POST", body: body || {}});
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const eur = n => n == null ? "" : "€ " + Math.round(n).toLocaleString("nl-NL");
const $ = s => document.querySelector(s);
function toast(msg) {
  let t = $(".toast"); if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.append(t); }
  t.textContent = msg; t.style.display = "block"; clearTimeout(t._h); t._h = setTimeout(() => t.style.display = "none", 2600);
}
function header(active) {
  const links = [["specialist.html", "Specialist"], ["teamlead.html", "Team lead"], ["backoffice.html", "Back office"],
                 ["/docs", "API"]];
  const h = document.createElement("header");
  h.innerHTML = `<b>Company brain</b><nav>${links.map(([u, n]) => `<a href="${u}" class="${n === active ? "on" : ""}">${n}</a>`).join("")}</nav>
    <span class="stage" id="stage">sandbox</span>`;
  document.body.prepend(h);
  api("/api/status").then(s => $("#stage").textContent = `synthetic data · model: ${s.model} · TravelSpirit: ${s.travelspirit}`);
}
const STATUS_CHIP = {new: "gold", proposal_draft: "orange", proposal_sent: "teal", booked: "teal", lost: "red",
  to_send: "gold", waiting: "orange", chased: "red", answered: "teal", declined: "red"};
const chip = (s) => `<span class="chip ${STATUS_CHIP[s] || ""}">${esc(s.replace("_", " "))}</span>`;
