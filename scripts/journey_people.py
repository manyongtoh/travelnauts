"""A specialist's day and a team lead's day, through the API as the screens use it.

  PYTHONPATH=. python scripts/journey_people.py

Mail arrives like real mail (an address and a text). Every step records what the person saw and could do, so
tests/test_journey_people.py can check the hand-offs. Explorative: written to find flow problems.
"""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timedelta

os.environ.setdefault("BRAIN_DATABASE_URL", "sqlite:////tmp/journey_people.db")
os.environ.setdefault("BRAIN_VAULT", "/tmp/journey-people-vault")
os.environ.setdefault("BRAIN_FILES", "/tmp/journey-people-files")
os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

from fastapi.testclient import TestClient
from sqlalchemy import select

from brain import clock, db, jobs
from brain.db import (
    Draft,
    Employee,
    Family,
    Job,
    KnowledgeGap,
    Mail,
    TripRequest,
)

T0 = datetime(2026, 11, 10, 7, 0)
log: list[dict] = []


def at(dt):
    clock.set_now(dt)


def note(who, what, **kw):
    log.append({"t": clock.utcnow().strftime("%a %H:%M"), "who": who, "what": what, **kw})
    if __name__ == "__main__":
        print(f"{log[-1]['t']}  {who:<12} {what}" + (f"  {json.dumps(kw, default=str)[:190]}" if kw else ""))


def tick():
    with db.session() as s:
        jobs.schedule_tick(s)
        for _ in range(10):
            if not jobs.work(s, limit=200):
                break


def mail(s, mid, sender, subject, body, when=None):
    s.add(Mail(id=mid, received_at=when or clock.utcnow(), sender=sender, subject=subject, body=body, status="new", truth={}))


def main():
    log.clear()
    from brain.synth.generate import build
    url = os.environ["BRAIN_DATABASE_URL"]
    if url.startswith("sqlite:///") and os.path.exists(url.removeprefix("sqlite:///")):
        os.remove(url.removeprefix("sqlite:///"))
    db.reset_engine()
    at(T0 - timedelta(days=1))
    build(seed=21, n_families=40, hard=False)
    from brain.api import app as appmod
    appmod._buckets.clear()
    c = TestClient(appmod.app, raise_server_exceptions=False)
    H = lambda uid: {"X-Brain-User": uid}

    with db.session() as s:
        for m in s.scalars(select(Mail).where(Mail.status == "new")).all():
            m.status = "done"  # a quiet inbox: only this day's mail
        spec = s.get(Employee, "sanne-de-vries")
        lead = s.scalars(select(Employee).where(Employee.role == "team_lead", Employee.team_id == spec.team_id)).first().id
        colleague = s.scalars(select(Employee).where(Employee.role == "specialist", Employee.team_id == spec.team_id,
                                                     Employee.id != spec.id, Employee.active.is_(True))).first().id
        admin = s.scalars(select(Employee).where(Employee.role == "admin")).first().id
        # Sanne's family with a proposal out (for a change request) and one travelling right now (for a complaint)
        sent = s.scalars(select(TripRequest).where(TripRequest.specialist_id == spec.id)).first()
        from brain.agents import proposal
        from brain.workflow import approve_draft
        at(T0 - timedelta(days=2))
        pd = proposal.write_proposal(s, sent.id)
        approve_draft(s, pd.id, spec.name, actor_id=spec.id)
        route = [r["stop"] for r in pd.data["route"]]
        at(T0 - timedelta(days=1))
        away = s.scalars(select(TripRequest).where(TripRequest.specialist_id == spec.id, TripRequest.id != sent.id)).first()
        away.status, away.depart_date = "booked", (T0 - timedelta(days=5)).date()
        f_sent, f_away = s.get(Family, sent.family_id), s.get(Family, away.family_id)
        unknown_fam = s.scalars(select(Family).where(Family.id.not_in([sent.family_id, away.family_id]))).first()
        s.commit()
        # overnight mail
        mail(s, "p-new", "j.dekker@kpnmail.example", "Rondreis Vietnam",
             "Hallo, wij willen in april drie weken naar Vietnam met onze kinderen van 7 en 10. Budget rond 11000 euro. "
             "Groet, Jasper Dekker", T0 - timedelta(hours=6))
        mail(s, "p-change", f_sent.email, "Re: Jullie reis",
             f"Hoi {spec.name.split()[0]}, mooi voorstel! Kunnen we een nacht minder in {route[0]} en een nacht langer "
             f"in {route[-1]}? Groet, {f_sent.contact_name}", T0 - timedelta(hours=5))
        mail(s, "p-question", f_sent.email, "Vraagje",
             f"Hallo, hebben we voor de kinderen een eigen paspoort nodig? Groet, {f_sent.contact_name}", T0 - timedelta(hours=4))
        mail(s, "p-complaint", f_away.email, "Transfer kwam niet",
             "We staan op het vliegveld en de transfer is er niet! Niemand neemt op. Wat moeten we doen?", T0 - timedelta(hours=1))
        mail(s, "p-unknown", "oma.dekker@hotmail.example", "Reis van mijn dochter",
             f"Goedemorgen, ik schrijf namens mijn dochter {unknown_fam.contact_name}. Kunnen jullie haar terugbellen "
             "over de reis? Met vriendelijke groet", T0 - timedelta(hours=3))
        s.commit()
        ids = {"sent": sent.id, "away": away.id, "unknown_fam": unknown_fam.id}

    at(T0)
    tick()

    # ------------------------------------------------------------------ the specialist's day
    at(T0 + timedelta(hours=1, minutes=30))
    reqs = c.get("/api/requests", headers=H(spec.id)).json()
    drafts = c.get("/api/drafts", headers=H(spec.id)).json()
    note("specialist", "opens Today", requests=len(reqs), drafts=sorted({d["kind"] for d in drafts}),
         new_request=any((r.get("mail_id") == "p-new") for r in reqs))
    with db.session() as s:
        m = s.get(Mail, "p-new")
        rid_new = (m.triage or {}).get("request_id")
        owner_new = s.get(TripRequest, rid_new).specialist_id if rid_new else None
        note("brain", "new request routed", team=(m.triage or {}).get("team_id"), owner=owner_new, to_sanne=owner_new == spec.id)
    who_new = owner_new or spec.id
    det = c.get(f"/api/requests/{rid_new}", headers=H(who_new)).json() if rid_new else {}
    prop = next((d for d in det.get("drafts", []) if d["kind"] == "proposal" and d["status"] == "draft"), None)
    note("specialist", "proposal for the new family waiting", ready=bool(prop), availability=det.get("availability"))
    if prop:
        edited = prop["body"].replace("Hallo", "Beste Jasper", 1) + "\n\nIk bel jullie morgen even."
        r = c.post(f"/api/drafts/{prop['id']}/approve", json={"final_body": edited}, headers=H(who_new))
        note("specialist", "edits and sends the proposal", status=r.status_code, detail=r.json().get("detail") if r.status_code != 200 else None,
             edit_share=r.json().get("edit_share"))

    det = c.get(f"/api/requests/{ids['sent']}", headers=H(spec.id)).json()
    ch = next((d for d in det.get("drafts", []) if d["kind"] == "change" and d["status"] == "draft"), None)
    note("brain", "change request drafted by itself", ready=bool(ch), changes_listed=len(det.get("changes", [])))
    if not ch and det.get("changes"):
        r = c.post(f"/api/mails/{det['changes'][0]['id']}/change", headers=H(spec.id))
        note("specialist", "asks the agent to apply the change", status=r.status_code)
        ch = r.json() if r.status_code == 200 else None
    if ch:
        r = c.post(f"/api/drafts/{ch['id']}/approve", json={}, headers=H(spec.id))
        note("specialist", "sends the changed proposal", status=r.status_code, detail=r.json().get("detail") if r.status_code != 200 else None)

    ans = [d for d in c.get("/api/drafts?kind=answer", headers=H(spec.id)).json() if d["request_id"] == ids["sent"] or True]
    with db.session() as s:
        q = s.get(Mail, "p-question")
        note("brain", "question triaged", category=(q.triage or {}).get("category"), request=(q.triage or {}).get("request_id"))
    ans = [d for d in ans if (d.get("data") or {}).get("mail_id") == "p-question"]
    note("specialist", "answer draft waiting", found=bool(ans), placeholder=bool(ans and "[schrijf hier" in ans[0]["body"].lower()))
    if ans:
        body = ans[0]["body"]
        if "[schrijf hier" in body.lower():
            r = c.post(f"/api/drafts/{ans[0]['id']}/approve", json={}, headers=H(spec.id))
            note("specialist", "tries to send the placeholder", status=r.status_code)
            body = body.split("[")[0] + "Ja, sinds 2012 heeft elk kind een eigen paspoort of ID-kaart nodig.\n\nGroet, Sanne"
        r = c.post(f"/api/drafts/{ans[0]['id']}/approve", json={"final_body": body}, headers=H(spec.id))
        note("specialist", "sends the answer", status=r.status_code, detail=r.json().get("detail") if r.status_code != 200 else None)

    r = c.post(f"/api/requests/{ids['sent']}/call-notes", headers=H(spec.id),
               json={"notes": "Gebeld met familie. Willen toch liever geen binnenlandse vlucht, liever de trein. Ze boeken waarschijnlijk volgende week."})
    note("specialist", "logs a phone call", status=r.status_code, kind=r.json().get("kind") if r.status_code == 200 else r.text[:120])

    r = c.post("/api/ask", headers=H(spec.id), json={"question": "Kun je in Laos met kinderen goed met de boot reizen?"})
    a = r.json()
    note("specialist", "asks the brain something it does not know", status=r.status_code, gap=bool(a.get("gap_id") or a.get("gap")),
         answered=bool(a.get("answer")) and not a.get("gap_id"))

    at(T0 + timedelta(hours=3))
    r = c.post(f"/api/requests/{rid_new}/alternatives", headers=H(who_new)) if rid_new else None
    note("specialist", "asks for quieter and cheaper versions", status=r.status_code if r else None)
    r = c.post(f"/api/requests/{rid_new}/gds", headers=H(who_new)) if rid_new else None
    note("specialist", "asks for booking commands", status=r.status_code if r else None)

    # ------------------------------------------------------------------ the team lead's day
    at(T0 + timedelta(hours=2))
    tl = c.get("/api/teamlead", headers=H(lead)).json()
    flagged = c.get("/api/inbox?status=flagged", headers=H(lead)).json()
    unlinked = c.get("/api/mails/unlinked", headers=H(lead)).json()
    comp = c.get("/api/complaints", headers=H(lead)).json()
    mine_c = [x for x in comp if (x.get("data") or {}).get("mail_id") == "p-complaint"]
    note("team lead", "opens the overview", teams=sorted(tl["teams"]), flagged=len(flagged),
         unknown_address=[u.get("id") for u in unlinked], complaint_seen=bool(mine_c),
         complaint=(mine_c[0].get("data") or {}).get("severity") if mine_c else None,
         travelling=(mine_c[0].get("data") or {}).get("while_travelling") if mine_c else None)
    with db.session() as s:
        cm = s.get(Mail, "p-complaint")
        note("brain", "urgent complaint handled how", category=(cm.triage or {}).get("category"), urgent=(cm.triage or {}).get("urgent"),
             request=(cm.triage or {}).get("request_id"), right_trip=(cm.triage or {}).get("request_id") == ids["away"])
    if mine_c:
        r = c.post(f"/api/drafts/{mine_c[0]['id']}/approve", json={}, headers=H(spec.id))
        note("specialist", "tries to send the urgent complaint reply", status=r.status_code)
        r = c.post(f"/api/drafts/{mine_c[0]['id']}/approve", json={}, headers=H(lead))
        note("team lead", "approves the complaint reply", status=r.status_code, detail=r.json().get("detail") if r.status_code != 200 else None)
    if any(u.get("id") == "p-unknown" for u in unlinked):
        r = c.post("/api/mails/p-unknown/link", headers=H(lead), json={"family_id": ids["unknown_fam"], "remember": False})
        note("team lead", "links grandma's mail to the family, without remembering the address", status=r.status_code)
        tick()
        with db.session() as s:
            m = s.get(Mail, "p-unknown")
            rid_u = (m.triage or {}).get("request_id")
            note("brain", "after linking", family=m.family_id, category=(m.triage or {}).get("category"), request=rid_u, status=m.status)

    # Sanne calls in sick for a week: her open work goes to a colleague
    at(T0 + timedelta(hours=4))
    with db.session() as s:
        open_ids = [t.id for t in s.scalars(select(TripRequest).where(TripRequest.specialist_id == spec.id,
                                                                       TripRequest.status.in_(["new", "proposal_draft", "proposal_sent", "change_requested"]))).all()]
        waiting_before = s.scalars(select(Draft).where(Draft.request_id.in_(open_ids), Draft.status == "draft")).all()
        loose_before = [d.id for d in s.scalars(select(Draft).where(Draft.status == "draft")).all() if (d.data or {}).get("specialist_id") == spec.id]
    moved = [c.post(f"/api/requests/{rid}/reassign", headers=H(lead), json={"specialist_id": colleague}).status_code for rid in open_ids]
    col_drafts = {d["id"] for d in c.get("/api/drafts", headers=H(colleague)).json()}
    sanne_drafts = {d["id"] for d in c.get("/api/drafts", headers=H(spec.id)).json()}
    note("team lead", "moves Sanne's open requests to a colleague", requests=len(open_ids), ok=moved.count(200),
         drafts_waiting=len(waiting_before), colleague_sees=len({d.id for d in waiting_before} & col_drafts),
         sanne_still_sees=len(sanne_drafts), loose_drafts_with_sanne=len(loose_before))
    with db.session() as s:
        jobs_owned = s.scalars(select(Draft).where(Draft.status == "draft")).all()
        stuck = [d.id for d in jobs_owned if (d.data or {}).get("specialist_id") == spec.id]
    note("brain", "drafts still addressed to Sanne after the move", n=len(stuck))

    kn = c.get("/api/knowledge?status=proposed", headers=H(lead)).json()
    items = kn if isinstance(kn, list) else kn.get("items", [])
    if items:
        r = c.post(f"/api/knowledge/{items[0]['id']}/approve", headers=H(lead), json={})
        note("team lead", "approves a knowledge note", status=r.status_code)
    gaps = c.get("/api/gaps", headers=H(lead)).json()
    g = gaps if isinstance(gaps, list) else gaps.get("gaps", [])
    note("team lead", "reads the gap list", open=len(g), laos=any("laos" in (x.get("question") or "").lower() for x in g))
    v = c.get("/api/value?days=7", headers=H(lead)).json()
    note("team lead", "checks the value page", requests=v["speed"]["requests"], sent_unchanged=v["quality"]["sent_unchanged_pct"],
         hours_saved=v["hours_saved_estimate"])

    # a colleague leaves: admin removes access, the team lead must see the orphaned work
    at(T0 + timedelta(hours=6))
    r = c.post(f"/api/admin/users/{colleague}", headers=H(admin), json={"active": False})
    tick()
    c.post("/api/jobs/run/team_insight", headers=H(lead))
    ti = c.get("/api/reports/team_insight", headers=H(lead)).json()
    alerts = c.get("/api/admin/alerts", headers=H(admin)).json()
    note("admin", "removes the colleague's access", status=r.status_code)
    note("team lead", "sees work without an owner", ownerless=sum(len(x.get("ownerless", [])) for x in (ti.get("teams") or {}).values()),
         alert=[a.get("key") or a.get("check") for a in (alerts if isinstance(alerts, list) else alerts.get("alerts", []))])

    with db.session() as s:
        note("summary", "end of day", failed_jobs=s.query(Job).filter(Job.status == "failed").count(),
             open_gaps=s.query(KnowledgeGap).filter(KnowledgeGap.status == "open").count())
    if __name__ == "__main__":
        pathlib.Path("/tmp/journey_people.json").write_text(json.dumps(log, indent=1, default=str))
    clock.reset()
    return log


if __name__ == "__main__":
    main()
