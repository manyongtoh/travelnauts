"""One family, first mail to next trip, through the API as each role. Prints a timeline.

  PYTHONPATH=. python scripts/journey.py           (fresh SQLite database in /tmp)

Explorative: it records who had to act, what told them to, and how long things waited, so flow problems show.
"""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timedelta

os.environ.setdefault("BRAIN_DATABASE_URL", "sqlite:////tmp/journey.db")
os.environ.setdefault("BRAIN_VAULT", "/tmp/journey-vault")
os.environ.setdefault("BRAIN_FILES", "/tmp/journey-files")
os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

from fastapi.testclient import TestClient
from sqlalchemy import select

from brain import clock, db, jobs
from brain.db import Draft, Employee, Job, Mail, TripRequest

T0 = datetime(2026, 11, 9, 8, 0)
log: list[dict] = []


def at(dt):
    clock.set_now(dt)


def note(who, what, **kw):
    log.append({"t": clock.utcnow().strftime("%a %H:%M"), "who": who, "what": what, **kw})
    print(f"{log[-1]['t']}  {who:<12} {what}" + (f"  {json.dumps(kw, default=str)[:160]}" if kw else ""))


def tick(label=""):
    with db.session() as s:
        jobs.schedule_tick(s)
        done = []
        for _ in range(10):
            d = jobs.work(s, limit=200)
            done += d
            if not d:
                break
    kinds = {}
    for d in done:
        kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    if kinds:
        note("worker", f"ran jobs {label}".strip(), jobs=kinds)
    return done


def main():
    log.clear()
    from brain.synth.generate import build
    url = os.environ["BRAIN_DATABASE_URL"]
    if url.startswith("sqlite:///") and os.path.exists(url.removeprefix("sqlite:///")):
        os.remove(url.removeprefix("sqlite:///"))
    db.reset_engine()
    at(T0 - timedelta(days=1))
    build(seed=11, n_families=40, hard=False)
    from brain.api.app import app
    c = TestClient(app, raise_server_exceptions=False)

    def as_(uid):
        return {"X-Brain-User": uid}

    with db.session() as s:
        es = s.scalars(select(Employee)).all()
        bo = next(e.id for e in es if e.role == "back_office")
        # a family we have never heard of, writing from their own address: no family id, like real mail
        for old in s.scalars(select(Mail).where(Mail.status == "new")).all():
            old.status = "triaged"  # an empty inbox, so this journey is the only work
        s.add(Mail(id="j-first", received_at=T0, sender="Familie.Visser@ziggo.example", status="new",
                   subject="Rondreis Zuid-Afrika met kinderen",
                   body="Hallo, wij zijn met twee volwassenen en twee kinderen van 8 en 11 en willen in juli drie weken "
                        "naar Zuid-Afrika. Budget ongeveer 12000 euro. Graag safari en strand. Groet, Marieke Visser", truth={}))
        s.commit()
        mail_id = "j-first"
    at(T0)
    note("family", "sends first mail", mail=mail_id)
    tick("after mail")
    with db.session() as s:
        m = s.get(Mail, mail_id)
        note("brain", "matched sender", family=m.family_id, new_relation=m.triage.get("new_relation"))
        rid = m.triage.get("request_id")
        tr = s.get(TripRequest, rid) if rid else None
        spec = tr.specialist_id if tr else None
        lead = next(e.id for e in s.scalars(select(Employee).where(Employee.role == "team_lead", Employee.team_id == tr.team_id)))
        note("brain", "triaged", category=m.triage.get("category"), request=rid, team=tr.team_id if tr else None,
             specialist=spec, status=tr.status if tr else None)
        drafts = s.scalars(select(Draft).where(Draft.request_id == rid)).all()
        note("brain", "drafts after triage", drafts=[(d.kind, d.status) for d in drafts])

    # specialist starts the day
    at(T0 + timedelta(hours=1))
    inbox = c.get("/api/requests", headers=as_(spec)).json()
    mine = [r for r in inbox if r["id"] == rid]
    note("specialist", "opens own requests", total=len(inbox), sees_new_one=bool(mine),
         fields=sorted(mine[0].keys())[:12] if mine else None)
    det = c.get(f"/api/requests/{rid}", headers=as_(spec)).json()
    note("specialist", "opens request", keys=sorted(det.keys()))
    if not any(d["kind"] == "proposal" for d in det.get("drafts", [])):
        r = c.post(f"/api/requests/{rid}/proposal", headers=as_(spec))
        note("specialist", "asks for a proposal by hand", status=r.status_code)
    r = c.post(f"/api/requests/{rid}/partners", headers=as_(spec))
    note("specialist", "asks partner desk for availability", status=r.status_code, body=str(r.json())[:200])

    # back office
    at(T0 + timedelta(hours=2))
    bov = c.get("/api/backoffice", headers=as_(bo)).json()
    note("back office", "opens back office", partner_drafts=bov.get("partner_drafts") or bov.get("counts"))
    pds = c.get("/api/drafts?status=draft", headers=as_(bo)).json()
    pd_ids = [d["id"] for d in pds if d["kind"] == "partner_request" and d.get("request_id") == rid]
    for did in pd_ids:
        c.post(f"/api/drafts/{did}/approve", json={}, headers=as_(bo))
    note("back office", "approves partner mails", n=len(pd_ids))

    # partners answer next day
    at(T0 + timedelta(days=1, hours=1))
    r = c.post("/api/jobs/simulate-replies", headers=as_(bo))
    note("partners", "reply", status=r.status_code)
    tick("after replies")
    det = c.get(f"/api/requests/{rid}", headers=as_(spec)).json()
    note("brain", "request after replies", status=det["request"]["status"],
         partners=[(p.get("partner_id"), p.get("status")) for p in det.get("partners", [])],
         drafts=[(d["kind"], d["status"]) for d in det.get("drafts", [])])

    # specialist sends proposal
    at(T0 + timedelta(days=1, hours=2))
    prop = next((d for d in det.get("drafts", []) if d["kind"] == "proposal" and d["status"] == "draft"), None)
    if prop:
        r = c.post(f"/api/drafts/{prop['id']}/approve", json={}, headers=as_(spec))
        if r.status_code == 422:  # rule "block": the proposal waits for the partners
            note("specialist", "proposal waits for partners", detail=r.json()["detail"][:90], availability=det.get("availability"))
            at(T0 + timedelta(days=2, hours=2))
            with db.session() as s:
                from brain.db import PartnerRequest
                for pr in s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == rid)).all():
                    pr.status, pr.offer, pr.answered_at = "answered", {"available": True, "price_eur": 900}, clock.utcnow()
                s.commit()
            r = c.post(f"/api/drafts/{prop['id']}/approve", json={}, headers=as_(spec))
        sent = c.get(f"/api/requests/{rid}", headers=as_(spec)).json()
        body = next((d.get("final_body") or "" for d in sent["drafts"] if d["id"] == prop["id"]), "")
        note("specialist", "approves and sends proposal", status=r.status_code,
             with_caveat="onder voorbehoud" in body, availability=sent.get("availability"))

    # silence: follow-up
    for d in (3, 5, 8):
        at(T0 + timedelta(days=d, hours=1))
        tick(f"day {d}")
    det = c.get(f"/api/requests/{rid}", headers=as_(spec)).json()
    note("brain", "follow-up after silence", drafts=[(d["kind"], d["status"]) for d in det.get("drafts", [])])

    # family books (in TravelSpirit), with flights
    at(T0 + timedelta(days=9))
    with db.session() as s:
        tr = s.get(TripRequest, rid)
        tr.status = "booked"
        tr.depart_date = (T0 + timedelta(days=40)).date()
        tr.flights = [{"FlightNumber": "KL0597", "Date": tr.depart_date.isoformat()}]  # another export's field names
        s.commit()
    note("travelspirit", "booking confirmed (by specialist in TravelSpirit)")
    tick("after booking")
    det = c.get(f"/api/requests/{rid}", headers=as_(spec)).json()
    note("brain", "what happened on booking", drafts=[(d["kind"], d["status"]) for d in det.get("drafts", [])])
    at(T0 + timedelta(days=10, hours=3))
    tick("next morning")
    det = c.get(f"/api/requests/{rid}", headers=as_(spec)).json()
    note("brain", "day after booking", drafts=[(d["kind"], d["status"]) for d in det.get("drafts", [])])
    with db.session() as s:  # partners confirm over the next days (sandbox: all answer)
        from brain.db import PartnerRequest
        for pr in s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == rid)).all():
            pr.status, pr.offer, pr.answered_at = "answered", {"available": True, "price_eur": 900}, clock.utcnow()
        s.commit()
    note("partners", "all confirm")

    # days before departure
    for d in (20, 30, 37, 39, 40):
        at(T0 + timedelta(days=d, hours=6))
        tick(f"day {d}")
    det = c.get(f"/api/requests/{rid}", headers=as_(spec)).json()
    note("brain", "before departure", drafts=[(d["kind"], d["status"]) for d in det.get("drafts", [])])

    # after the trip: complaint
    at(T0 + timedelta(days=58))
    with db.session() as s:
        tr = s.get(TripRequest, rid)
        fam = tr.family_id
        s.add(Mail(id="j-complaint", received_at=clock.utcnow(), sender="familie.visser@ziggo.example",
                   subject="Teleurgesteld over ons hotel", status="new",
                   body="Het tweede hotel was vies en de kamer was te klein voor ons gezin. We willen graag een vergoeding.",
                   truth={}))
        s.commit()
    note("family", "complains after the trip")
    tick("after complaint")
    tl = c.get("/api/complaints", headers=as_(lead)).json()
    items = tl if isinstance(tl, list) else tl.get("items", tl.get("complaints", []))
    mine = [x for x in items if (x.get("data") or {}).get("mail_id") == "j-complaint" or x.get("mail_id") == "j-complaint"]
    note("team lead", "sees complaint", found=bool(mine), linked_request=[x.get("request_id") for x in mine])
    with db.session() as s:
        m = s.get(Mail, "j-complaint")
        note("brain", "complaint triage", family=m.family_id, category=m.triage.get("category"))

    at(T0 + timedelta(days=130))
    tick("months later")
    det = c.get(f"/api/requests/{rid}", headers=as_(spec)).json()
    with db.session() as s:
        nt = [d for d in s.scalars(select(Draft).where(Draft.kind == "next_trip")).all() if (d.data or {}).get("family_id") == fam]
    note("brain", "next trip idea for this family", drafted=bool(nt))
    with db.session() as s:
        note("summary", "jobs failed", n=s.query(Job).filter(Job.status == "failed").count())
    if __name__ == "__main__":
        pathlib.Path("/tmp/journey.json").write_text(json.dumps(log, indent=1, default=str))
    clock.reset()
    return log


if __name__ == "__main__":
    main()
