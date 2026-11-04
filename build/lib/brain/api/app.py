"""HTTP API and the three screens (specialist, team lead, back office)."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from .. import db
from ..agents import followup, galileo, knowledge_desk, partner_desk, proposal, triage
from ..config import get_settings
from ..db import AgentRun, Draft, Employee, Family, KnowledgeGap, KnowledgeItem, Mail, TripRequest, as_dict
from ..knowledge.store import KnowledgeBase
from ..synth.world import DESTINATIONS
from ..workflow import approve_draft, backoffice_overview, reject_draft, teamlead_overview

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Travelnauts company brain (sandbox)", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def _startup() -> None:
    db.create_all()
    with db.session() as s:
        db.assert_synthetic_only(s)


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/static/index.html")


@app.get("/api/status")
def status():
    st = get_settings()
    with db.session() as s:
        return {"model": st.model, "triage_model": st.triage_model, "data_stage": st.data_stage,
                "travelspirit": st.travelspirit_mode, "travelspirit_write": st.travelspirit_write,
                "families": s.query(Family).count(), "mails": s.query(Mail).count(),
                "knowledge": s.query(KnowledgeItem).count()}


# Inbox and requests ---------------------------------------------------------------------------

@app.get("/api/inbox")
def inbox(status: str | None = None):
    with db.session() as s:
        q = select(Mail).order_by(Mail.received_at.desc())
        if status:
            q = q.where(Mail.status == status)
        return [{k: v for k, v in as_dict(m).items() if k != "truth"} for m in s.scalars(q).all()]


@app.post("/api/triage")
def triage_all(limit: int | None = None):
    with db.session() as s:
        return triage.triage_inbox(s, limit)


@app.post("/api/mails/{mail_id}/triage")
def triage_one(mail_id: str):
    with db.session() as s:
        try:
            return triage.triage_mail(s, mail_id)
        except KeyError:
            _404("mail")


@app.get("/api/requests")
def requests(team: str | None = None, specialist: str | None = None):
    with db.session() as s:
        q = select(TripRequest).order_by(TripRequest.created_at.desc())
        if team:
            q = q.where(TripRequest.team_id == team)
        if specialist:
            q = q.where(TripRequest.specialist_id == specialist)
        out = []
        for r in s.scalars(q).all():
            f = s.get(Family, r.family_id)
            out.append(as_dict(r) | {"family": f.contact_name, "child_ages": f.child_ages, "adults": f.adults,
                                      "destination_name": DESTINATIONS[r.destination]["name"]})
        return out


@app.get("/api/requests/{rid}")
def request_detail(rid: str):
    with db.session() as s:
        r = s.get(TripRequest, rid) or _404("request")
        f = s.get(Family, r.family_id)
        drafts = [as_dict(d) for d in s.scalars(select(Draft).where(Draft.request_id == rid).order_by(Draft.id)).all()]
        mail = s.get(Mail, r.mail_id) if r.mail_id else None
        return {"request": as_dict(r) | {"destination_name": DESTINATIONS[r.destination]["name"]}, "family": as_dict(f),
                "drafts": [d for d in drafts if d["kind"] in ("proposal", "followup", "galileo", "answer")],
                "mail": {k: v for k, v in as_dict(mail).items() if k != "truth"} if mail else None,
                "partners": partner_desk.compare_offers(s, rid)}


@app.post("/api/requests/{rid}/proposal")
def make_proposal(rid: str):
    with db.session() as s:
        return as_dict(proposal.write_proposal(s, rid))


@app.post("/api/requests/{rid}/galileo")
def make_galileo(rid: str):
    with db.session() as s:
        return as_dict(galileo.write_commands(s, rid))


@app.post("/api/requests/{rid}/partners")
def make_partner_requests(rid: str):
    with db.session() as s:
        try:
            return [as_dict(p) for p in partner_desk.plan_partner_requests(s, rid)]
        except ValueError as e:
            raise HTTPException(400, str(e))


# Scheduled jobs (in production these run on a timer) -----------------------------------------

@app.post("/api/jobs/followups")
def job_followups():
    with db.session() as s:
        return [as_dict(d) for d in followup.run_followups(s)]


@app.post("/api/jobs/chases")
def job_chases():
    with db.session() as s:
        return [as_dict(partner_desk.draft_chase(s, p.id)) for p in partner_desk.due_chases(s)]


@app.post("/api/jobs/simulate-replies")
def job_simulate():
    with db.session() as s:
        return {"answered": partner_desk.simulate_replies(s)}


# Drafts ---------------------------------------------------------------------------------------

class Decision(BaseModel):
    by: str
    final_body: str | None = None
    reason: str = ""


@app.get("/api/drafts")
def drafts(kind: str | None = None, status: str | None = "draft"):
    with db.session() as s:
        q = select(Draft).order_by(Draft.id.desc())
        if kind:
            q = q.where(Draft.kind.in_(kind.split(",")))
        if status:
            q = q.where(Draft.status == status)
        return [as_dict(d) for d in s.scalars(q).all()]


@app.post("/api/drafts/{did}/approve")
def approve(did: int, d: Decision):
    with db.session() as s:
        try:
            return as_dict(approve_draft(s, did, d.by, d.final_body))
        except KeyError:
            _404("draft")
        except ValueError as e:
            raise HTTPException(409, str(e))


@app.post("/api/drafts/{did}/reject")
def reject(did: int, d: Decision):
    with db.session() as s:
        return as_dict(reject_draft(s, did, d.by, d.reason))


# Knowledge ------------------------------------------------------------------------------------

class Question(BaseModel):
    question: str
    destination: str | None = None
    team_id: str | None = None


@app.post("/api/ask")
def ask(q: Question):
    with db.session() as s:
        return knowledge_desk.ask(s, q.question, q.destination, q.team_id)


@app.get("/api/knowledge")
def knowledge(status: str | None = None, destination: str | None = None):
    with db.session() as s:
        q = select(KnowledgeItem).order_by(KnowledgeItem.id)
        if status:
            q = q.where(KnowledgeItem.status == status)
        if destination:
            q = q.where(KnowledgeItem.destination == destination)
        owners = {e.id: e.name for e in s.scalars(select(Employee)).all()}
        return [as_dict(k) | {"owner": owners.get(k.owner_id)} for k in s.scalars(q).all()]


class Approval(BaseModel):
    by: str


@app.post("/api/knowledge/{kid}/approve")
def approve_knowledge(kid: str, a: Approval):
    with db.session() as s:
        try:
            return as_dict(KnowledgeBase(s).approve(kid, a.by))
        except KeyError:
            _404("knowledge item")


@app.get("/api/gaps")
def gaps(team: str | None = None):
    with db.session() as s:
        return [as_dict(g) for g in KnowledgeBase(s).gaps(team)]


# Overviews and audit -------------------------------------------------------------------------

@app.get("/api/teamlead")
def teamlead():
    with db.session() as s:
        return teamlead_overview(s)


@app.get("/api/backoffice")
def backoffice():
    with db.session() as s:
        return backoffice_overview(s)


@app.get("/api/employees")
def employees():
    with db.session() as s:
        return [as_dict(e) for e in s.scalars(select(Employee).order_by(Employee.name)).all()]


@app.get("/api/audit")
def audit_log(limit: int = 100):
    with db.session() as s:
        return [as_dict(a) for a in s.scalars(select(AgentRun).order_by(AgentRun.id.desc()).limit(limit)).all()]


@app.post("/api/reset")
def reset(seed: int | None = None):
    from ..synth.generate import build
    return build(seed or get_settings().seed)
