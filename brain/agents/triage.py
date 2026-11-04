"""Triage: read a new mail, say what it is, pull out the trip details, route it to the right team.

Pilot model choice: Gemma (BRAIN_TRIAGE_MODEL). New requests become a TripRequest assigned to the
specialist in that team with the fewest open requests.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import Employee, Mail, Team, TripRequest
from ..synth.world import DESTINATIONS
from .common import audit, run_step

Category = Literal["new_request", "change", "question", "complaint", "partner_reply", "other"]


class TriageResult(BaseModel):
    category: Category
    urgent: bool = False
    destination: str | None = Field(None, description="one of the destination keys in CONTEXT, or null")
    adults: int | None = None
    child_ages: list[int] = []
    days: int | None = None
    month: str | None = Field(None, description="departure month in Dutch, lower case")
    budget_eur: float | None = None
    wishes: list[str] = []
    summary: str = Field(description="one line in Dutch for the specialist")


INSTRUCTIONS = (
    "Classify the mail in CONTEXT.mail. Categories: new_request (a new trip), change (change to an existing proposal or "
    "booking), question (a general question), complaint, partner_reply, other (newsletters, invoices, spam). "
    "Mark urgent for complaints, and when the family asks for a quick answer. Extract trip details only if stated."
)


def team_for(s: Session, destination: str | None) -> Team | None:
    if not destination:
        return None
    for t in s.scalars(select(Team)).all():
        if destination in t.destinations:
            return t
    return None


def least_loaded_specialist(s: Session, team_id: str) -> Employee | None:
    open_count = (select(TripRequest.specialist_id, func.count().label("n"))
                  .where(TripRequest.status.in_(["new", "proposal_draft", "proposal_sent"]))
                  .group_by(TripRequest.specialist_id).subquery())
    q = (select(Employee).outerjoin(open_count, open_count.c.specialist_id == Employee.id)
         .where(Employee.team_id == team_id, Employee.role == "specialist")
         .order_by(func.coalesce(open_count.c.n, 0), Employee.id))
    return s.scalars(q).first()


def triage_mail(s: Session, mail_id: str) -> dict:
    m = s.get(Mail, mail_id)
    if m is None:
        raise KeyError(mail_id)
    with audit(s, "triage", mail_id, m.subject) as box:
        ctx = {"mail": {"from": m.sender, "subject": m.subject, "body": m.body},
               "destinations": {k: v["nl"] for k, v in DESTINATIONS.items()}}
        res, _ = run_step("triage", TriageResult, INSTRUCTIONS, ctx, get_settings().triage_model)
        team = team_for(s, res.destination)
        out = res.model_dump()
        out["team_id"] = team.id if team else None
        if res.category == "new_request" and m.family_id and res.destination:
            spec = least_loaded_specialist(s, team.id) if team else None
            n = s.scalar(select(func.count()).select_from(TripRequest)) or 0
            tr = TripRequest(id=f"r{n + 1:03d}", family_id=m.family_id, mail_id=m.id, team_id=team.id if team else None,
                             specialist_id=spec.id if spec else None, destination=res.destination, days=res.days or 21,
                             depart_month=res.month or "onbekend", budget_eur=res.budget_eur, wishes=res.wishes,
                             status="new", last_customer_contact=m.received_at)
            s.add(tr)
            out["request_id"] = tr.id
            out["specialist_id"] = tr.specialist_id
        m.triage = out
        m.status = "triaged"
        s.commit()
        box["output"] = f"{res.category} {res.destination or ''} team={out['team_id']}"
    return out


def triage_inbox(s: Session, limit: int | None = None) -> list[dict]:
    ids = [m.id for m in s.scalars(select(Mail).where(Mail.status == "new").order_by(Mail.received_at)).all()]
    return [triage_mail(s, i) for i in ids[:limit]]
