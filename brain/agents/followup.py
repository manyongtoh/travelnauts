"""Follow-up: proposals sent a while ago without a reply get a friendly draft reminder."""
from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import Draft, Employee, Family, TripRequest
from ..identity import agent
from ..toolserver import server
from ..synth.world import DESTINATIONS
from .common import audit, run_step
from ..clock import utcnow

ME = agent("follow_up")


class FollowUpText(BaseModel):
    subject: str
    body: str


INSTRUCTIONS = (
    "Write a short, friendly follow-up in Dutch to CONTEXT.family about the proposal for CONTEXT.trip. No pressure. "
    "Offer to adjust the route or to call. If CONTEXT.knowledge has a season fact, you may use it as a light reason to "
    "decide soon. At most six sentences."
)


def due_followups(s: Session, now: datetime | None = None) -> list[TripRequest]:
    now = now or utcnow()
    cutoff = now - timedelta(days=get_settings().followup_after_days)
    rows = s.scalars(select(TripRequest).where(TripRequest.status == "proposal_sent", TripRequest.proposal_sent_at <= cutoff)).all()
    done = {d.request_id for d in s.scalars(select(Draft).where(Draft.kind == "followup")).all()}
    return [r for r in rows if r.id not in done and (r.last_customer_contact is None or r.last_customer_contact <= cutoff)]


def write_followup(s: Session, request_id: str) -> Draft:
    tr = s.get(TripRequest, request_id)
    fam = s.get(Family, tr.family_id)
    spec = s.get(Employee, tr.specialist_id) if tr.specialist_id else None
    d = DESTINATIONS[tr.destination]
    with audit(s, "follow_up", request_id) as box:
        hits = server.call(s, ME, "knowledge.search", query=f"beste reistijd {d['nl']}", destination=tr.destination, k=1)
        days_since = (utcnow() - tr.proposal_sent_at).days if tr.proposal_sent_at else None
        ctx = {"family": {"name": fam.contact_name, "child_ages": fam.child_ages},
               "trip": {"destination": d["nl"], "days": tr.days, "month": tr.depart_month},
               "days_since_proposal": days_since, "specialist": spec.name if spec else "Travelnauts",
               "knowledge": [{"id": h["id"], "text": h["body"]} for h in hits]}
        out, _ = run_step(s, "followup", FollowUpText, INSTRUCTIONS, ctx)
        draft = Draft(kind="followup", request_id=tr.id, title=out.subject, body=out.body,
                      sources=[{"type": "knowledge", **{k: v for k, v in h.items() if k != "body"}} for h in hits],
                      data={"days_since": days_since})
        s.add(draft)
        s.commit()
        box["sources"] = draft.sources
        box["output"] = out.subject
    return draft


def run_followups(s: Session) -> list[Draft]:
    return [write_followup(s, r.id) for r in due_followups(s)]
