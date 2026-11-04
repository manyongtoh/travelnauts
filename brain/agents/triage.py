"""Triage: read a new mail, say what it is, pull out the trip details, route it to the right team.

Order of work:
  1. Injection check on the raw mail. A suspicious mail is flagged for a person; no agent drafts on it.
  2. Small model classifies and extracts. If it is unsure, or the mail is a complaint, the large model
     looks again (escalation by rule).
  3. New requests become a dossier for the least busy specialist in the team; change requests are linked
     to the family's trip.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import Employee, Mail, Team, TripRequest
from ..guardrails import detect_injection
from ..identity import agent
from ..synth.world import DESTINATIONS
from ..toolserver import server
from .common import audit, run_step

Category = Literal["new_request", "change", "question", "complaint", "partner_reply", "invoice", "other"]
ME = agent("triage")


class TriageResult(BaseModel):
    category: Category
    urgent: bool = False
    confidence: float = Field(0.9, ge=0, le=1, description="how sure you are of the category, 0 to 1")
    destination: str | None = Field(None, description="one of the destination keys in CONTEXT, or null")
    adults: int | None = None
    child_ages: list[int] = []
    days: int | None = None
    month: str | None = Field(None, description="departure month in Dutch, lower case")
    budget_eur: float | None = None
    wishes: list[str] = []
    summary: str = Field(description="at most three short lines in Dutch for the specialist")


INSTRUCTIONS = (
    "Classify the mail in CONTEXT.mail. Categories: new_request (a new trip), change (change to an existing proposal or "
    "booking), question (a general question), complaint, partner_reply (a hotel or local partner answering a request), "
    "invoice (a supplier invoice), "
    "other (newsletters, invoices, out of office, spam). Mark urgent for complaints and when the family asks for a quick "
    "answer. Extract trip details only if stated. Give your confidence."
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
                  .where(TripRequest.status.in_(["new", "proposal_draft", "proposal_sent", "change_requested"]))
                  .group_by(TripRequest.specialist_id).subquery())
    q = (select(Employee).outerjoin(open_count, open_count.c.specialist_id == Employee.id)
         .where(Employee.team_id == team_id, Employee.role == "specialist", Employee.active.is_(True))
         .order_by(func.coalesce(open_count.c.n, 0), Employee.id))
    return s.scalars(q).first()


def triage_mail(s: Session, mail_id: str) -> dict:
    m = s.get(Mail, mail_id)
    if m is None:
        raise KeyError(mail_id)
    if m.status != "new":  # safe to repeat: a mail is triaged once
        return (m.triage or {}) | {"skipped": "already triaged"}
    with audit(s, "triage", mail_id, m.subject) as box:
        mail = server.call(s, ME, "ts.read_mail", mail_id=mail_id)
        attachment_text = ""
        for a in (m.attachments or []):  # instructions can hide in an attachment just as well as in the mail
            if a.get("mime") == "application/pdf":
                from ..files import pdf_text
                try:
                    attachment_text += "\n" + pdf_text(a["path"])[:20000]
                except Exception:  # noqa: BLE001  an unreadable PDF is suspicious too
                    attachment_text += "\n[unreadable attachment]"
        inj = detect_injection(f"{mail['subject']}\n{mail['body']}{attachment_text}")
        if "[unreadable attachment]" in attachment_text:
            inj = inj | {"flagged": True, "reasons": inj["reasons"] + ["unreadable_attachment"]}
        if inj["flagged"]:
            out = {"category": "flagged", "flagged": True, "injection": inj, "team_id": None,
                   "summary": "Mogelijk gemanipuleerde mail: een collega kijkt ernaar, geen concept gemaakt"}
            m.triage, m.status = out, "flagged"
            s.commit()
            box["output"] = f"flagged {','.join(inj['reasons'])}"
            return out
        from ..anonymise import FREEMAIL
        domain = (mail["sender"] or "").rsplit("@", 1)[-1].lower()
        sender = "freemail" if domain in FREEMAIL or not domain else domain  # the domain says who, without naming a person
        ctx = {"mail": {"from": sender, "subject": mail["subject"], "body": mail["body"]},
               "destinations": {k: v["nl"] for k, v in DESTINATIONS.items()}}
        res, _ = run_step(s, "triage", TriageResult, INSTRUCTIONS, ctx)
        escalated = False
        if res.confidence < 0.6 or res.category == "complaint":
            res, _ = run_step(s, "triage", TriageResult, INSTRUCTIONS, ctx, tier="large", escalated=True)
            escalated = True
        team = team_for(s, res.destination)
        out = res.model_dump() | {"team_id": team.id if team else None, "escalated": escalated}
        if not m.family_id:  # real mail carries an address, not a family: match it, or open a new relation
            fam = resolve_family(s, m.sender, res, m.body)  # the stored address; the model only ever sees the domain
            if fam is not None:
                m.family_id = fam.id
                out["new_relation"] = fam.id.startswith("f-new-")
            elif res.category in ("change", "complaint"):
                out["unknown_sender"] = True  # a person links it to the right family
        if res.category == "new_request" and m.family_id and res.destination:
            spec = least_loaded_specialist(s, team.id) if team else None
            from ..db import next_number
            n = next_number(s, "request", start_from=s.scalar(select(func.count()).select_from(TripRequest)) or 0)
            tr = TripRequest(id=f"r{n:03d}", family_id=m.family_id, mail_id=m.id, team_id=team.id if team else None,
                             specialist_id=spec.id if spec else None, destination=res.destination, days=res.days or 21,
                             depart_month=res.month or "onbekend", budget_eur=res.budget_eur, wishes=res.wishes,
                             status="new", last_customer_contact=m.received_at)
            s.add(tr)
            out["request_id"] = tr.id
            out["specialist_id"] = tr.specialist_id
        if res.category == "change" and m.family_id:
            from .change import latest_version
            trips = [s.get(TripRequest, t["id"]) for t in server.call(s, ME, "ts.list_trips", family_id=m.family_id)]
            cands = [t for t in trips if latest_version(s, t.id)]
            cands.sort(key=lambda t: (t.status not in ("proposal_sent", "change_requested"),
                                      t.destination != res.destination, -t.created_at.timestamp()))
            tr = cands[0] if cands else None
            if tr:
                if len(cands) > 1 and cands[1].status == tr.status and cands[1].destination == tr.destination:
                    out["ambiguous_trip"] = True
                out.update(request_id=tr.id, team_id=tr.team_id, specialist_id=tr.specialist_id)
                tr.status = "change_requested"
                tr.last_customer_contact = m.received_at
        from ..jobs import enqueue
        if out.get("request_id") and res.category == "new_request":
            enqueue(s, "write_proposal", {"request_id": out["request_id"]})  # the draft is ready when the specialist looks
        if res.category == "partner_reply" and m.partner_id:
            enqueue(s, "partner_reply", {"mail_id": m.id})
        if res.category == "invoice":
            enqueue(s, "invoice", {"mail_id": m.id})
        if res.category == "complaint" and m.family_id:
            enqueue(s, "complaint", {"mail_id": m.id})
        if m.family_id and res.category not in ("partner_reply", "invoice"):
            for t in s.scalars(select(TripRequest).where(TripRequest.family_id == m.family_id,
                                                          TripRequest.status == "proposal_sent")).all():
                t.last_customer_contact = m.received_at  # they wrote back: a reminder from us would cross their mail
        m.triage = out
        m.status = "triaged"
        s.commit()
        if m.family_id:
            from ..workflow import withdraw_stale_drafts
            withdraw_stale_drafts(s)
        box["output"] = f"{res.category} {res.destination or ''} team={out['team_id']}{' escalated' if escalated else ''}"
    return out


def triage_inbox(s: Session, limit: int | None = None) -> list[dict]:
    ids = [m.id for m in s.scalars(select(Mail).where(Mail.status == "new").order_by(Mail.received_at)).all()]
    return [triage_mail(s, i) for i in ids[:limit]]


SIGN_OFF = re.compile(r"(?i:groet(?:en)?|groetjes|vriendelijke groet(?:en)?|hartelijke groet(?:en)?|liefs|regards)[,!.]?\s*\n?\s*"
                      r"([A-Z][a-z\u00e0-\u00ff]+(?:(?:\s+(?:van|de|der|den|ter|ten|het|'t)){0,3}\s+[A-Z][a-z\u00e0-\u00ff'-]+)*)\s*$")


def name_from_sign_off(body: str | None) -> tuple[str, str]:
    """'Groet, Marieke van der Berg' gives ('Marieke van der Berg', 'van der Berg'). Nothing found gives ('', '')."""
    lines = [ln for ln in (body or "").strip().splitlines()
             if not re.match(r"\s*(verstuurd (vanaf|met)|sent from|get outlook|op .* schreef)", ln, re.I)]
    m = SIGN_OFF.search("\n".join(lines).strip()[-200:])
    if not m:
        return "", ""
    full = " ".join(m.group(1).split())
    parts = full.split(" ", 1)
    return full, (parts[1] if len(parts) > 1 else "")


def resolve_family(s: Session, sender: str | None, res, body: str | None = None) -> "Family | None":
    """Which family wrote this? By exact address (case-insensitive) against the relations. A first enquiry from an
    unknown address opens a new relation, marked for the specialist to check and create in TravelSpirit."""
    from ..db import Family, next_number
    addr = (sender or "").strip().lower()
    if not addr or "@" not in addr:
        return None
    fam = s.scalars(select(Family).where(func.lower(Family.email) == addr)).first()
    if fam is not None or res.category != "new_request":
        return fam
    n = next_number(s, "new_relation")
    name, surname = name_from_sign_off(body)
    fam = Family(id=f"f-new-{n:04d}", surname=surname, contact_name=name, email=addr, adults=res.adults or 2,
                 child_ages=list(res.child_ages or []), notes="Nieuwe relatie uit een eerste mail: controleer en maak aan in TravelSpirit.",
                 synthetic=False)
    s.add(fam)
    s.flush()
    return fam
