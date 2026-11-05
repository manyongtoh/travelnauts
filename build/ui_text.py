"""Collect every English text a person can see on the screens, so the Dutch dictionary covers them.
Usage: python build/ui_text.py out.json [en|nl]  (needs playwright)"""
import json, os, re, socket, subprocess, sys, tempfile, time, urllib.request

tmp = tempfile.mkdtemp()
LANG = sys.argv[2] if len(sys.argv) > 2 else "en"
env = os.environ | {"BRAIN_DATABASE_URL": f"sqlite:///{tmp}/x.db", "BRAIN_VAULT": f"{tmp}/v", "BRAIN_FILES": f"{tmp}/f",
                    "PYDANTIC_AI_NO_BANNER": "1", "BRAIN_MODEL": "sandbox", "BRAIN_TRIAGE_MODEL": "sandbox"}
subprocess.run([sys.executable, "-c", """
from brain.synth.generate import build
from brain import db, jobs
from brain.agents import triage
build(seed=5, n_families=40, hard=True)
with db.session() as s:
    triage.triage_inbox(s)
    for _ in range(4): jobs.work(s)
"""], env=env, check=True)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "brain.api.app:app", "--port", str(port)], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(120):
    try: urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1); break
    except Exception: time.sleep(0.5)
JS = """() => { const out = new Set(); const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = w.nextNode())) { const p = n.parentElement; if (!p || ['SCRIPT','STYLE','TEXTAREA'].includes(p.tagName)) continue;
    const t = n.nodeValue.trim(); if (t) out.add(t); }
  document.querySelectorAll('[placeholder],[aria-label],[title]').forEach(e => ['placeholder','aria-label','title'].forEach(a => e.getAttribute(a) && out.add(e.getAttribute(a).trim())));
  return [...out]; }"""
found = {}
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for user, screen in [("sanne-de-vries", "specialist"), ("marloes-kuiper", "teamlead"), ("ruben-stam", "backoffice"),
                         ("myt-beheer", "maintenance"), ("myt-beheer", "users"), (None, "index")]:
        pg = b.new_page()
        pg.goto(f"http://127.0.0.1:{port}/static/index.html")
        if user: pg.evaluate(f"localStorage.setItem('me', '{user}')")
        pg.evaluate(f"localStorage.setItem('lang', '{LANG}'); localStorage.setItem('lang:{user or ''}', '{LANG}')")
        pg.goto(f"http://127.0.0.1:{port}/static/{screen}.html"); pg.wait_for_timeout(1200)
        views = pg.eval_on_selector_all(".nav-btn", "bs => bs.map(b => b.dataset.view)") or [None]
        for v in views:
            if v: pg.click(f'.nav-btn[data-view="{v}"]'); pg.wait_for_timeout(700)
            for t in pg.evaluate(JS): found.setdefault(t, f"{screen}:{v}")
            rows = pg.query_selector_all("#view .list li.row:not(.row-head), #view .card[data-id], #view [data-open]")
            for r in rows[:2]:
                try: r.click(timeout=800); pg.wait_for_timeout(500)
                except Exception: continue
                for t in pg.evaluate(JS): found.setdefault(t, f"{screen}:{v}:detail")
        pg.close()
    b.close()
proc.terminate()
json.dump(found, open(sys.argv[1], "w"), ensure_ascii=False, indent=0)
print(len(found))
