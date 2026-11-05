"""The back office day for one trip: partner requests, replies, chasing, invoices, booking file and roadbook.

  PYTHONPATH=. python scripts/journey_backoffice.py

Partner mail arrives like real mail: an address and a text, no partner id filled in. Prints a timeline and
returns it, so tests/test_journey_backoffice.py can check every hand-off.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

os.environ.setdefault("BRAIN_DATABASE_URL", "sqlite:////tmp/journey_bo.db")
os.environ.setdefault("BRAIN_VAULT", "/tmp/journey-bo-vault")
os.environ.setdefault("BRAIN_FILES", "/tmp/journey-bo-files")
os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brain.tenant import tenant
from brain import clock, db, jobs  # noqa: E402
from brain.db import Draft, Employee, Job, Mail, Partner, PartnerRequest, TripRequest  # noqa: E402

T0 = datetime(2026, 11, 9, 8, 0)
log: list[dict] = []


def at(dt):
    clock.set_now(dt)


def note(who, what, **kw):
    log.append({"t": clock.utcnow().strftime("%a %d %H:%M"), "who": who, "what": what, **kw})
    if __name__ == "__main__":
        print(f"{log[-1]['t']}  {who:<12} {what}" + (f"  {json.dumps(kw, default=str)[:170]}" if kw else ""))


def tick():
    with db.session() as s:
        jobs.schedule_tick(s)
        for _ in range(10):
            if not jobs.work(s, limit=200):
                break


def main():
    log.clear()
    from brain.synth.generate import build
    url = os.environ["BRAIN_DATABASE_URL"]
    if url.startswith("sqlite:///") and os.path.exists(url.removeprefix("sqlite:///")):
        os.remove(url.removeprefix("sqlite:///"))
    db.reset_engine()
    at(T0 - timedelta(days=1))
    build(seed=12, n_families=40, hard=False)
    from brain.api.app import app
    c = TestClient(app, raise_server_exceptions=False)
    H = lambda uid: {"X-Brain-User": uid}  # noqa: E731
    with db.session() as s:
        for m in s.scalars(select(Mail).where(Mail.status == "new")).all():
            m.status = "done"  # a quiet inbox: only this journey's mail
        bo = s.scalars(select(Employee).where(Employee.role == "back_office")).first().id
        tr = s.scalars(select(TripRequest).where(TripRequest.status == "new")).first()
        rid, spec = tr.id, tr.specialist_id
        s.commit()

    # Monday: the specialist has a proposal and asks partners
    at(T0)
    from brain.agents import proposal
    with db.session() as s:
        proposal.write_proposal(s, rid)
    r = c.post(f"/api/requests/{rid}/partners", headers=H(spec))
    note("specialist", "asks partners for availability", status=r.status_code, partners=len(r.json()))
    at(T0 + timedelta(hours=1))
    board = c.get("/api/backoffice", headers=H(bo)).json()
    mine = [x for x in board["cards"] if x["request_id"] == rid]
    note("back office", "opens the board", cards=len(mine), with_draft=sum(bool(x["draft_id"]) for x in mine),
         statuses=sorted({x["status"] for x in mine}))
    for x in mine:
        if not x["draft_id"]:
            c.post(f"/api/partner-requests/{x['id']}/draft", headers=H(bo))
    board = c.get("/api/backoffice", headers=H(bo)).json()
    sent = 0
    for x in [x for x in board["cards"] if x["request_id"] == rid and x["draft_id"]]:
        sent += c.post(f"/api/drafts/{x['draft_id']}/approve", json={}, headers=H(bo)).status_code == 200
    note("back office", "sends the partner mails", sent=sent)

    with db.session() as s:
        prs = s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == rid).order_by(PartnerRequest.id)).all()
        parts = [(pr.id, s.get(Partner, pr.partner_id)) for pr in prs]
    ref = tenant().reference(rid)

    # Tuesday: replies arrive the way partners write them
    at(T0 + timedelta(days=1, hours=1))
    replies = []
    with db.session() as s:
        (pa_id, pa), (pb_id, pb), (pc_id, pc) = parts[0], parts[1], parts[2]
        dom = lambda p: p.email.split("@")[1]  # noqa: E731
        replies = [
            ("bo-r1", f"reservations@{dom(pa)}", f"RE: Availability request {ref}",
             f"Dear {tenant().short_name},\n\nYes, we can confirm availability for {ref}. Total price EUR 1.240 for the family room.\n\nKind regards,\nReservations"),
            ("bo-r2", pb.email, "RE: Availability request",  # no reference at all
             "Hello,\n\nSorry, we are fully booked on those dates. Could we offer the week after instead?\n\nBest,\nMaria"),
            ("bo-r3", f"info@{dom(pc)}", f"RE: {ref}",
             "Hi, thanks for your request. We need to check with the owner and will come back to you."),
        ]
        for mid, frm, subj, body in replies:
            s.add(Mail(id=mid, received_at=clock.utcnow(), sender=frm, subject=subj, body=body, status="new", truth={}))
        s.commit()
    tick()
    with db.session() as s:
        for mid, *_ in replies:
            m = s.get(Mail, mid)
            note("brain", f"partner reply {mid}", category=(m.triage or {}).get("category"), partner=m.partner_id, status=m.status)
        for pr_id, p in parts[:3]:
            pr = s.get(PartnerRequest, pr_id)
            note("brain", f"request to {p.kind} {p.name}", status=pr.status, offer=pr.offer)
    det = c.get(f"/api/requests/{rid}", headers=H(spec)).json()
    note("specialist", "sees availability", availability=det.get("availability"))
    with db.session() as s:
        alt = s.scalars(select(Draft).where(Draft.request_id == rid, Draft.kind == "alternatives")).first()
    note("brain", "alternative for the partner that said no", drafted=bool(alt))

    # Friday: chasing the partners that did not answer
    for d in (3, 4, 7):
        at(T0 + timedelta(days=d, hours=2))
        tick()
    with db.session() as s:
        chases = s.scalars(select(Draft).where(Draft.kind == "partner_chase", Draft.status == "draft")).all()
        mine = [d for d in chases if (d.data or {}).get("request_id") == rid or d.request_id == rid]
    note("brain", "chase mails drafted", n=len(mine))
    for d in mine:
        c.post(f"/api/drafts/{d.id}/approve", json={}, headers=H(bo))
    at(T0 + timedelta(days=14, hours=2))
    tick()
    with db.session() as s:
        still = [(s.get(Partner, pr.partner_id).name, pr.status, (utcnow_ := clock.utcnow()) and (utcnow_ - pr.sent_at).days if pr.sent_at else None)
                 for pr in s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == rid)).all()
                 if pr.status in ("waiting", "chased")]
        chases2 = [d for d in s.scalars(select(Draft).where(Draft.kind == "partner_chase")).all() if d.request_id == rid]
    note("brain", "two weeks later, still no answer", partners=still, chases_total=len(chases2))

    # booked; invoices come in
    at(T0 + timedelta(days=15))
    with db.session() as s:
        t = s.get(TripRequest, rid)
        t.status, t.depart_date = "booked", (T0 + timedelta(days=60)).date()
        s.commit()
    with db.session() as s:
        inv = [
            ("bo-i1", f"accounts@{dom(pa)}", f"Invoice 2026-118 {ref}", f"Invoice 2026-118\nReference {ref}\nTotal EUR 1.240\nPayment within 30 days"),
            ("bo-i2", f"accounts@{dom(pa)}", f"Invoice 2026-118 {ref} (reminder)", f"Invoice 2026-118\nReference {ref}\nTotal EUR 1.240\nPayment within 30 days"),
            ("bo-i3", f"billing@{dom(parts[3][1])}" if len(parts) > 3 else "billing@other.example", f"Invoice 77 {ref}",
             f"Invoice 77\nReference {ref}\nTotal EUR 2.150\nPayment within 14 days"),
        ]
        for mid, frm, subj, body in inv:
            s.add(Mail(id=mid, received_at=clock.utcnow(), sender=frm, subject=subj, body=body, status="new", truth={}))
        s.commit()
    tick()
    rows = c.get("/api/invoices", headers=H(bo)).json()
    rows = rows if isinstance(rows, list) else rows.get("items", [])
    for mid, *_ in inv:
        x = next((r for r in rows if r.get("mail_id") == mid), None)
        note("brain", f"invoice {mid}", status=x and x["status"], expected=x and x.get("expected_eur"), partner=x and x.get("partner_id"),
             note=x and x.get("note"))

    # three weeks before departure: booking file and roadbook
    at(T0 + timedelta(days=40, hours=3))
    tick()
    rep = c.get("/api/reports/booking_check", headers=H(bo)).json()
    f = next((x for x in rep.get("files", []) if x["request_id"] == rid), None)
    note("back office", "booking file check", missing=f and f["missing"])
    with db.session() as s:
        rb = s.scalars(select(Draft).where(Draft.request_id == rid, Draft.kind == "roadbook")).first()
        note("brain", "roadbook", drafted=bool(rb), vouchers=rb and len((rb.data or {}).get("vouchers", [])))
        note("summary", "jobs failed", n=s.query(Job).filter(Job.status == "failed").count(),
             errors=[(j.kind, (j.error or "")[:80]) for j in s.query(Job).filter(Job.status == "failed").all()][:3])
    clock.reset()
    return log


if __name__ == "__main__":
    main()
