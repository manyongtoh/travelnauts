"""Screenshots for the demo walkthrough, the portal one-pager and the local agent guide.
  PYTHONPATH=. python build/screenshots.py /tmp/shots
Builds a day of work with scripts/journey_people.py, then photographs the screens."""
import os, socket, subprocess, sys, time, urllib.request
from datetime import timedelta
from pathlib import Path

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
os.environ.update(BRAIN_DATABASE_URL="sqlite:////tmp/shots.db", BRAIN_VAULT="/tmp/shots-vault", BRAIN_FILES="/tmp/shots-files",
                  PYDANTIC_AI_NO_BANNER="1", BRAIN_MODEL="sandbox", BRAIN_TRIAGE_MODEL="sandbox")
import importlib.util
spec = importlib.util.spec_from_file_location("jp", "scripts/journey_people.py"); jp = importlib.util.module_from_spec(spec); spec.loader.exec_module(jp)
jp.main()
from sqlalchemy import select
from brain import db, portal
from brain.agents import partner_desk, proposal
from brain.clock import utcnow
from brain.db import Draft, Partner, PartnerRequest, Setting, TripRequest
db.reset_engine()
with db.session() as s:
    tr = next(t for t in s.scalars(select(TripRequest).where(TripRequest.specialist_id == "ruud-martens", TripRequest.depart_date.is_(None))).all()
              if s.scalars(select(Partner).where(Partner.destination == t.destination, Partner.kind == "local_agent")).first())
    if not s.scalars(select(Draft).where(Draft.request_id == tr.id, Draft.kind == "proposal")).first():
        proposal.write_proposal(s, tr.id)
    p = s.scalars(select(Partner).where(Partner.destination == tr.destination, Partner.kind == "local_agent")).first()
    pr = s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == tr.id, PartnerRequest.partner_id == p.id)).first()
    if pr is None:
        pr = PartnerRequest(request_id=tr.id, partner_id=p.id, what="Transfers and excursions", status="waiting", sent_at=utcnow())
        s.add(pr); s.commit()
    pr.status, pr.sent_at = "waiting", utcnow()
    s.commit()
    url = portal.issue_link(s, pr)
    lines = s.scalars(select(portal.PortalLine).where(portal.PortalLine.partner_request_id == pr.id).order_by(portal.PortalLine.position)).all()
    link = portal.open_link(s, url.rsplit("/", 1)[1])
    soon = (utcnow() + timedelta(days=45)).date()
    portal.update_line(s, link, lines[0].id, "confirmed", 85, soon, "Driver waits in arrivals with a name sign")
    portal.update_line(s, link, lines[1].id, "asking", note="Asking the boat owner, answer tomorrow")
    tl = next(x for x in lines[2:] if x.label.startswith("Transfer"))
    portal.update_line(s, link, tl.id, "alternative", alternative={"label": tl.label + " by private car instead of train", "price_eur": 140, "note": "Train sold out that week"})
    portal.add_message(s, pr.id, "partner", "", "Is the youngest child still in a car seat?")
    portal.add_message(s, pr.id, portal.TEAM, "Ruben Stam", "Yes, one child seat please. Thanks!")
    prid, token, spec_id = pr.id, url.rsplit("/", 1)[1], tr.specialist_id
    s.merge(Setting(key=f"autosend:{spec_id}:followup", value={"status": "on", "streak": 10, "on_by": spec_id, "on_at": utcnow().replace(microsecond=0).isoformat()}))
    from brain.db import Family
    a = next(f for f in s.scalars(select(Family).order_by(Family.id)).all() if f.child_birth_years and f.city)
    s.add(Family(id="fam950", surname=a.surname, contact_name="P. " + a.surname, email="p." + a.surname.lower().replace(" ", "") + "@kpn.example",
                 adults=2, child_ages=list(a.child_ages), child_birth_years=list(a.child_birth_years), city=a.city, synthetic=True))
    for f in s.scalars(select(Family).where(Family.synthetic.is_(False))).all():
        f.synthetic = True  # relations the journey opened from its made-up mail: synthetic too
    s.commit()
sk = socket.socket(); sk.bind(("127.0.0.1", 0)); port = sk.getsockname()[1]; sk.close()
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "brain.api.app:app", "--port", str(port)], env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(120):
    try: urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1); break
    except Exception: time.sleep(0.5)
base = f"http://127.0.0.1:{port}"
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch()
    def page(user, path, w=1440, h=900, lang="en"):
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
        ctx.add_init_script(f"localStorage.setItem('me','{user}'); localStorage.setItem('lang','{lang}'); localStorage.setItem('lang:{user}','{lang}')")
        pg = ctx.new_page(); pg.goto(base + path); pg.wait_for_timeout(1500); return pg
    # portal, partner side, on a phone
    pg = page("", f"/portal/{token}", 390, 844); pg.screenshot(path=str(out / "portal-phone.png"), full_page=False)
    pg.screenshot(path=str(out / "portal-phone-full.png"), full_page=True)
    pg = page("", f"/portal/{token}", 1100, 900); pg.screenshot(path=str(out / "portal-desktop.png"))
    # back office panel
    pg = page("ruben-stam", "/static/backoffice.html"); pg.screenshot(path=str(out / "backoffice-board.png"))
    pg.evaluate(f"openPortal({prid})"); pg.wait_for_timeout(1200); pg.screenshot(path=str(out / "backoffice-portal-panel.png"))
    # specialist: today, a proposal, and a follow-up counting down
    pg = page("ruud-martens", "/static/specialist.html"); pg.screenshot(path=str(out / "specialist-today.png"))
    with db.session() as s:
        s.add(Draft(kind="followup", request_id=tr.id, title="Nog vragen over jullie reis?", body="Hallo,\n\nHebben jullie al naar het voorstel kunnen kijken?\n\nGroet", data={}))
        s.commit()
    pg.wait_for_timeout(4000); pg.screenshot(path=str(out / "autosend-countdown.png"))
    pg = page("sanne-de-vries", "/static/specialist.html", lang="nl"); pg.screenshot(path=str(out / "specialist-today-nl.png"))
    # team lead
    for view in ("overview", "complaints", "value", "duplicates"):
        pg = page("marloes-kuiper", "/static/teamlead.html")
        pg.click(f'[data-view="{view}"]'); pg.wait_for_timeout(1200); pg.screenshot(path=str(out / f"teamlead-{view}.png"))
    b.close()
proc.terminate()
print(sorted(p.name for p in out.iterdir()))
