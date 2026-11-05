"""Demo: one family's journey through the company brain, as screenshots and a short screen recording.

  PYTHONPATH=. python build/demo.py build/demo

Runs on synthetic data in real time against a local server, step by step as the people would work: the family
mails, the proposal is ready, partners answer in the portal, the family asks a change, books, and writes from
the road. Each step leaves a screenshot and a short clip with a caption; the clips are joined into demo.mp4.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "build/demo").resolve()
shutil.rmtree(OUT, ignore_errors=True)
(OUT / "clips").mkdir(parents=True)
os.environ.update(BRAIN_DATABASE_URL="sqlite:////tmp/demo.db", BRAIN_VAULT="/tmp/demo-vault", BRAIN_FILES="/tmp/demo-files",
                  PYDANTIC_AI_NO_BANNER="1", BRAIN_MODEL="sandbox", BRAIN_TRIAGE_MODEL="sandbox", BRAIN_AUTOSEND_HOLD="10")
for f in ("/tmp/demo.db", "/tmp/demo.db-wal", "/tmp/demo.db-shm"):
    if os.path.exists(f):
        os.remove(f)

from sqlalchemy import select  # noqa: E402

from brain import db  # noqa: E402
from brain.clock import utcnow  # noqa: E402
from brain.db import Draft, Employee, Mail, Partner, PartnerRequest, TripRequest  # noqa: E402
from brain.synth.generate import build  # noqa: E402

db.reset_engine()
build(seed=11, n_families=40, hard=False)
with db.session() as s:
    for m in s.scalars(select(Mail).where(Mail.status == "new")).all():
        m.status = "done"
    lead_of = {e.team_id: e.id for e in s.scalars(select(Employee).where(Employee.role == "team_lead")).all()}
    bo = s.scalars(select(Employee).where(Employee.role == "back_office")).first().id
    s.commit()

sk = socket.socket(); sk.bind(("127.0.0.1", 0)); PORT = sk.getsockname()[1]; sk.close()
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "brain.api.app:app", "--port", str(PORT)], env=os.environ.copy(),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
BASE = f"http://127.0.0.1:{PORT}"
for _ in range(120):
    try:
        urllib.request.urlopen(BASE + "/healthz", timeout=1); break
    except Exception:
        time.sleep(0.5)


def call(method, path, user=None, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body or {}).encode() if method == "POST" else None,
                                 headers={"Content-Type": "application/json", **({"X-Brain-User": user} if user else {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b"null")


def tick(user):
    call("POST", "/api/triage", user)  # the inbox poll runs every 5 minutes; read the new mail now
    for _ in range(4):
        call("POST", "/api/jobs/tick", user)


from playwright.sync_api import sync_playwright  # noqa: E402

CAPTION = """(t) => { let c = document.getElementById('demo-cap'); if (!c) { c = document.createElement('div'); c.id = 'demo-cap';
  c.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:99;background:#1F2A44;color:#fff;'
   + 'font:600 19px/1.35 Instrument Sans,system-ui,sans-serif;padding:12px 20px;border-radius:12px;max-width:80%;text-align:center;'
   + 'box-shadow:0 8px 28px rgba(0,0,0,.25)'; if (innerWidth < 600) { c.style.fontSize = '13px'; c.style.maxWidth = '92%'; c.style.bottom = '14px'; c.style.padding = '8px 12px'; }
  document.body.append(c); } c.textContent = t; }"""
steps: list[dict] = []


def shoot(pw, name, user, path, caption, act=None, w=1440, h=900, lang="nl", hold=5500, mobile=False):
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1 if not mobile else 2,
                              record_video_dir=str(OUT / "clips"), record_video_size={"width": 1440, "height": 900} if not mobile else {"width": 390, "height": 844})
    ctx.add_init_script(f"localStorage.setItem('me','{user or ''}'); localStorage.setItem('lang','{lang}'); localStorage.setItem('lang:{user or ''}','{lang}')")
    pg = ctx.new_page()
    pg.goto(BASE + path)
    pg.wait_for_timeout(1500)
    if act:
        act(pg)
        pg.wait_for_timeout(900)
    pg.evaluate(CAPTION, caption)
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(OUT / f"{name}.png"))
    pg.wait_for_timeout(hold)
    video = pg.video.path()
    ctx.close(); browser.close()
    clip = OUT / "clips" / f"{len(steps):02d}-{name}.webm"
    Path(video).rename(clip)
    steps.append({"name": name, "caption": caption, "clip": clip.name, "mobile": mobile})


def open_item(rid, scroll=True):
    def act(pg):
        if pg.query_selector(f'.ditem[data-id="{rid}"]'):
            pg.click(f'.ditem[data-id="{rid}"]')
            pg.wait_for_timeout(900)
        if scroll:  # show the draft, not the mail above it
            pg.evaluate("(document.querySelector('#detail textarea.c-text') || document.querySelector('#detail .concept'))?.scrollIntoView({block: 'start'}); scrollBy(0, -120)")
    return act


import atexit  # noqa: E402
atexit.register(server.terminate)  # never leave a server holding the database

with sync_playwright() as pw:
    # 1. A new family mails; the brain reads it and drafts the proposal before anyone looks
    with db.session() as s:
        s.add(Mail(id="demo-1", received_at=utcnow(), sender="marieke.visser@ziggo.example", status="new",
                   subject="Rondreis Zuid-Afrika met kinderen",
                   body="Hallo,\n\nWij zijn met twee volwassenen en twee kinderen van 8 en 11 en willen in juli drie weken naar "
                        "Zuid-Afrika. Budget ongeveer 12000 euro. Graag safari en strand.\n\nGroet,\nMarieke Visser", truth={}))
        s.commit()
    tick(lead_of["africa"])
    with db.session() as s:
        m = s.get(Mail, "demo-1")
        rid = m.triage["request_id"]
        tr = s.get(TripRequest, rid)
        spec, lead = tr.specialist_id, lead_of[tr.team_id]
    shoot(pw, "01-proposal-ready", spec, "/static/specialist.html",
          "1 · Marieke Visser mails at night. In the morning the request is sorted, routed and the proposal is drafted.", open_item(rid))

    # 2. The specialist asks partners; the back office sends the requests (each mail carries a portal link)
    call("POST", f"/api/requests/{rid}/partners", spec)
    for d in call("GET", "/api/drafts?kind=partner_request", bo):
        if d["request_id"] == rid:
            call("POST", f"/api/drafts/{d['id']}/approve", bo)
    shoot(pw, "02-backoffice-board", bo, "/static/backoffice.html",
          "2 · One click asks the local agent and every hotel. The back office approves the requests on the board.", lang="en")

    # 3. The local agent answers line by line in the portal
    with db.session() as s:
        pr = next(p for p in s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == rid)).all()
                  if s.get(Partner, p.partner_id).kind == "local_agent")
        d = s.scalars(select(Draft).where(Draft.partner_request_id == pr.id)).first()
        token = re.search(r"/portal/([\w-]+)", d.body).group(1)
        prid = pr.id
        hotel_prs = [p.id for p in s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == rid)).all() if p.id != pr.id]
    v = call("GET", f"/api/portal/{token}")
    valid = (utcnow() + timedelta(days=60)).date().isoformat()
    lines = v["lines"]
    for i, ln in enumerate(lines):
        if i == 1:
            call("POST", f"/api/portal/{token}/lines/{ln['id']}", None, {"status": "asking", "note": "Asking the lodge, answer tomorrow"})
        elif i == 2 and ln["label"].startswith("Transfer"):
            call("POST", f"/api/portal/{token}/lines/{ln['id']}", None, {"status": "alternative", "alternative": {"label": ln["label"] + " with a family van and driver", "price_eur": 260}})
        else:
            call("POST", f"/api/portal/{token}/lines/{ln['id']}", None, {"status": "confirmed", "price_eur": 90 + 15 * i, "valid_until": valid})
    shoot(pw, "03-portal-phone", None, f"/portal/{token}", "3 · The local agent answers on a phone, line by line. No account.",
          w=390, h=844, lang="en", mobile=True)
    shoot(pw, "04-portal-panel", bo, "/static/backoffice.html", "4 · The back office sees each answer at once and accepts an alternative in one click.",
          lambda pg: pg.evaluate(f"openPortal({prid})"), lang="en")
    for ln in call("GET", f"/api/partner-requests/{prid}/portal", bo)["lines"]:
        if ln["status"] == "alternative":
            call("POST", f"/api/partner-requests/{prid}/lines/{ln['id']}/accept", bo)
        if ln["status"] == "asking":
            call("POST", f"/api/portal/{token}/lines/{ln['id']}", None, {"status": "confirmed", "price_eur": 180, "valid_until": valid})
    with db.session() as s:
        for p in s.scalars(select(PartnerRequest).where(PartnerRequest.id.in_(hotel_prs))).all():
            p.status, p.offer, p.answered_at = "answered", {"available": True, "price_eur": 900}, utcnow()
        s.commit()

    # 4. The specialist sends the proposal; the family asks a change; the new version is ready before she looks
    prop = next(d for d in call("GET", f"/api/requests/{rid}", spec)["drafts"] if d["kind"] == "proposal" and d["status"] == "draft")
    call("POST", f"/api/drafts/{prop['id']}/approve", spec, {"final_body": prop["body"]})
    route = [r["stop"] for r in prop["data"]["route"]]
    with db.session() as s:
        s.add(Mail(id="demo-2", received_at=utcnow(), sender="marieke.visser@ziggo.example", status="new", subject="Re: jullie voorstel",
                   body=f"Hoi,\n\nMooi voorstel! Kunnen we een nacht minder in {route[0]} en een nacht langer in {route[-1]}?\n\nGroet,\nMarieke", truth={}))
        s.commit()
    tick(lead)
    shoot(pw, "05-change-ready", spec, "/static/specialist.html",
          f"5 · \"A night less in {route[0]}\": the brain recalculates and drafts the new version.", open_item(rid))
    ch = next(d for d in call("GET", f"/api/requests/{rid}", spec)["drafts"] if d["kind"] == "change" and d["status"] == "draft")
    call("POST", f"/api/drafts/{ch['id']}/approve", spec)

    # 5. Booked: extras are offered by themselves
    with db.session() as s:
        t = s.get(TripRequest, rid)
        t.status, t.depart_date = "booked", (utcnow() + timedelta(days=45)).date()
        s.commit()
    call("POST", "/api/jobs/run/booking_check", lead)
    tick(lead)
    shoot(pw, "06-extras", spec, "/static/specialist.html", "6 · Booked. Extras that fit the route and the children's ages are suggested by themselves.",
          open_item(rid))

    # 6. On the road: the transfer does not show up
    with db.session() as s:
        t = s.get(TripRequest, rid)
        t.depart_date = (utcnow() - timedelta(days=4)).date()
        s.add(Mail(id="demo-3", received_at=utcnow(), sender="marieke.visser@ziggo.example", status="new", subject="Transfer",
                   body="We staan op het vliegveld en de transfer is er niet! Niemand neemt op. Wat moeten we doen?", truth={}))
        s.commit()
    tick(lead)
    shoot(pw, "07-urgent", lead, "/static/teamlead.html",
          "7 · A message from the road is urgent: linked to the running trip, high priority, the team lead approves the reply.",
          lambda pg: pg.click('[data-view="complaints"]'))

    # 7. What it is worth
    shoot(pw, "08-value", lead, "/static/teamlead.html", "8 · The value page: time to first proposal, work done unprompted, hours saved. Per team, never per person.",
          lambda pg: pg.click('[data-view="value"]'))

server.terminate()

# join the clips: same size, a short pause between them
lst = OUT / "clips" / "list.txt"
parts = []
for st in steps:
    src = OUT / "clips" / st["clip"]
    mp4 = src.with_suffix(".mp4")
    vf = "scale=1440:900:force_original_aspect_ratio=decrease,pad=1440:900:(ow-iw)/2:(oh-ih)/2:color=0xF3ECE2,fps=25"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ss", "1.2", "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-an", str(mp4)], check=True)
    parts.append(mp4)
lst.write_text("".join(f"file '{p}'\n" for p in parts))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(OUT / "demo.mp4")], check=True)
(OUT / "steps.json").write_text(json.dumps(steps, indent=1))
print(OUT / "demo.mp4", len(steps), "steps")
