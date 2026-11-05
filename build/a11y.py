"""Accessibility and usability scan: axe-core (WCAG 2.1 AA) on every view of every screen, plus keyboard checks.
  PYTHONPATH=. python build/a11y.py /path/to/axe.min.js out.json
Uses the database left by build/screenshots.py (/tmp/shots.db)."""
import json, os, subprocess, sys, time, urllib.request
AXE = open(sys.argv[1]).read()
env = os.environ | {"BRAIN_DATABASE_URL": "sqlite:////tmp/shots.db", "BRAIN_VAULT": "/tmp/shots-vault", "BRAIN_FILES": "/tmp/shots-files", "PYDANTIC_AI_NO_BANNER": "1"}
p = subprocess.Popen([sys.executable, "-m", "uvicorn", "brain.api.app:app", "--port", "8812"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(60):
    try: urllib.request.urlopen("http://127.0.0.1:8812/healthz", timeout=1); break
    except Exception: time.sleep(0.5)
B = "http://127.0.0.1:8812"
SCREENS = [("ruud-martens", "specialist", ["today", "trips", "ask", "log"]), ("ruben-stam", "backoffice", None),
           ("marloes-kuiper", "teamlead", None), ("myt-beheer", "maintenance", None), ("myt-beheer", "users", None), ("", "index", [None])]
results = {}
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for lang in ("en", "nl"):
        for user, screen, views in SCREENS:
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(f"localStorage.setItem('me','{user}');localStorage.setItem('lang','{lang}');localStorage.setItem('lang:{user}','{lang}')")
            pg = ctx.new_page(); pg.goto(f"{B}/static/{screen}.html"); pg.wait_for_timeout(1500)
            vs = views or pg.eval_on_selector_all(".nav-btn", "x => x.map(b => b.dataset.view)") or [None]
            for v in vs:
                if v: pg.click(f'.nav-btn[data-view="{v}"]'); pg.wait_for_timeout(900)
                pg.evaluate(AXE)
                r = pg.evaluate("""async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}})).violations
                  .map(v => ({id: v.id, impact: v.impact, help: v.help, n: v.nodes.length, nodes: v.nodes.slice(0, 4).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\\n').slice(1, 2).join(''))}))""")
                results[f"{lang}:{screen}:{v}"] = r
            ctx.close()
    # keyboard: can the specialist reach and see focus on the main actions?
    ctx = b.new_context(viewport={"width": 1440, "height": 900}); ctx.add_init_script("localStorage.setItem('me','ruud-martens')")
    pg = ctx.new_page(); pg.goto(f"{B}/static/specialist.html"); pg.wait_for_timeout(1500)
    seen = []
    for _ in range(40):
        pg.keyboard.press("Tab")
        seen.append(pg.evaluate("() => { const e = document.activeElement; const s = getComputedStyle(e); return [e.tagName, (e.innerText || e.getAttribute('aria-label') || e.id || '').trim().slice(0, 40), s.outlineStyle !== 'none' || s.boxShadow !== 'none'] }"))
    results["keyboard:specialist"] = seen
    # portal on a phone
    import sqlite3
    b.close()
p.terminate()
json.dump(results, open(sys.argv[2], "w"), indent=1)
summary = {}
for k, vs in results.items():
    if k.startswith("keyboard"): continue
    for v in vs:
        s = summary.setdefault(v["id"], {"impact": v["impact"], "help": v["help"], "where": [], "nodes": v["nodes"]})
        s["where"].append(k)
for k, s in sorted(summary.items(), key=lambda x: ["critical", "serious", "moderate", "minor", None].index(x[1]["impact"])):
    print(f"{s['impact']:9} {k}: {s['help']} ({len(s['where'])} views)  e.g. {s['nodes'][:2]}")
