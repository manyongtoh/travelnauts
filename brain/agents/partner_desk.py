"""Partner desk (back office): writes availability requests to partners, keeps track of who has
answered, drafts reminders, and compares offers. Back office approves every mail before it goes."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import Draft, Family, Partner, PartnerRequest, TripRequest
from ..synth.world import DESTINATIONS
from .common import audit, run_step
from ..tenant import tenant
from ..clock import utcnow


class PartnerMail(BaseModel):
    subject: str
    body: str


REQUEST_INSTRUCTIONS = (
    "Write a short, clear availability request in English to CONTEXT.partner for CONTEXT.trip. Include travel month, "
    "nights, number of adults and the ages of the children, and room needs. Ask for price, availability and "
    "cancellation terms. Sign as CONTEXT.signature. No customer names, use the booking reference."
)
CHASE_INSTRUCTIONS = (
    "Write a polite, short reminder in English to CONTEXT.partner about the request with reference CONTEXT.reference "
    "sent on CONTEXT.sent_at. Ask for an answer within two working days."
)


def plan_partner_requests(s: Session, request_id: str) -> list[PartnerRequest]:
    """Open one request per partner needed: the local agent plus every hotel on the route."""
    tr = s.get(TripRequest, request_id)
    from .change import latest_version
    proposal = latest_version(s, request_id)
    if proposal is None:
        raise ValueError(f"No proposal for {request_id}")
    route = proposal.data["route"]
    wanted = [(p.id, "Transfers and excursions") for p in s.scalars(select(Partner).where(
        Partner.destination == tr.destination, Partner.kind == "local_agent")).all()]
    for r in route:
        p = s.scalars(select(Partner).where(Partner.name == r["hotel"])).first()
        if p:
            wanted.append((p.id, "Room availability and price"))
    existing = {(pr.partner_id) for pr in s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == request_id)).all()}
    created = []
    for pid, what in wanted:
        if pid in existing:
            continue
        pr = PartnerRequest(request_id=request_id, partner_id=pid, what=what, status="to_send")
        s.add(pr)
        created.append(pr)
    s.commit()
    for pr in created:
        draft_request_mail(s, pr.id)
    return created


def current_requests(s: Session, request_id: str) -> list[PartnerRequest]:
    """The partner requests that still matter: the local agent, and hotels that are on the latest version of the
    route. A hotel that said no and was replaced by another no longer counts against the trip."""
    from .change import latest_version
    prs = list(s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == request_id)).all())
    v = latest_version(s, request_id)
    if v is None:
        return prs
    hotels = {r.get("hotel") for r in v.data.get("route", []) if r.get("hotel")}
    out = []
    for pr in prs:
        p = s.get(Partner, pr.partner_id)
        if p is None or p.kind != "hotel" or p.name in hotels:
            out.append(pr)
    return out


def draft_request_mail(s: Session, partner_request_id: int) -> Draft:
    pr = s.get(PartnerRequest, partner_request_id)
    tr = s.get(TripRequest, pr.request_id)
    fam = s.get(Family, tr.family_id)
    partner = s.get(Partner, pr.partner_id)
    from .change import latest_version
    proposal = latest_version(s, tr.id)
    nights = next((r["nights"] for r in (proposal.data["route"] if proposal else []) if r["hotel"] == partner.name), None)
    with audit(s, "partner_desk", f"{tr.id}/{partner.id}", "request") as box:
        ctx = {"partner": {"name": partner.name, "kind": partner.kind}, "reference": tenant().reference(tr.id), "signature": tenant().back_office_signature,
               "trip": {"destination": DESTINATIONS[tr.destination]["name"], "month": tr.depart_month, "nights": nights,
                        "adults": fam.adults, "child_ages": fam.child_ages,
                        "rooms": "one family room" if fam.adults + len(fam.child_ages) <= 4 else "two connecting rooms",
                        "what": pr.what}}
        out, _ = run_step(s, "partner_request", PartnerMail, REQUEST_INSTRUCTIONS, ctx)
        from ..portal import issue_link
        url = issue_link(s, pr)  # added by the brain, never by the model: a link is not something to make up
        body = (out.body.rstrip() + f"\n\nYou can answer line by line here (prices, status, alternatives, no login needed):\n{url}\n"
                f"Reference {ctx['reference']}. Replying to this mail works too.")
        d = Draft(kind="partner_request", request_id=tr.id, partner_request_id=pr.id, title=out.subject, body=body,
                  data={"to": partner.email, "portal": True, "system_added": [url]})
        s.add(d)
        s.commit()
        box["output"] = out.subject
    return d


def mark_sent(s: Session, partner_request_id: int, when: datetime | None = None) -> None:
    pr = s.get(PartnerRequest, partner_request_id)
    pr.status = "waiting"
    pr.sent_at = when or utcnow()
    s.commit()


def due_chases(s: Session, now: datetime | None = None) -> list[PartnerRequest]:
    now = now or utcnow()
    cutoff = now - timedelta(days=get_settings().chase_partner_after_days)
    due = s.scalars(select(PartnerRequest).where(PartnerRequest.status == "waiting", PartnerRequest.sent_at <= cutoff)).all()
    # a partner busy in the portal (some lines answered, the rest 'asking the hotel') is working on it: no reminder
    return [pr for pr in due if not ((pr.offer or {}).get("portal_activity_at")
                                     and datetime.fromisoformat(pr.offer["portal_activity_at"]) > cutoff)]


def draft_chase(s: Session, partner_request_id: int) -> Draft:
    pr = s.get(PartnerRequest, partner_request_id)
    partner = s.get(Partner, pr.partner_id)
    with audit(s, "partner_desk", f"{pr.request_id}/{partner.id}", "chase") as box:
        ctx = {"partner": {"name": partner.name}, "reference": tenant().reference(pr.request_id), "signature": tenant().back_office_signature,
               "sent_at": pr.sent_at.date().isoformat() if pr.sent_at else None, "what": pr.what}
        out, _ = run_step(s, "partner_chase", PartnerMail, CHASE_INSTRUCTIONS, ctx)
        d = Draft(kind="partner_chase", request_id=pr.request_id, partner_request_id=pr.id, title=out.subject,
                  body=out.body, data={"to": partner.email})
        s.add(d)
        pr.status = "chased"
        pr.chased_at = utcnow()
        s.commit()
        box["output"] = out.subject
    return d


def compare_offers(s: Session, request_id: str) -> list[dict]:
    """Rank answered offers per kind of partner: available first, then price, then reliability."""
    rows = []
    for pr in s.scalars(select(PartnerRequest).where(PartnerRequest.request_id == request_id)).all():
        p = s.get(Partner, pr.partner_id)
        from ..partner_scores import scores
        sc = scores(p)
        rows.append({"partner_request_id": pr.id, "partner": p.name, "kind": p.kind, "status": pr.status, "what": pr.what,
                     "available": (pr.offer or {}).get("available"), "price_eur": (pr.offer or {}).get("price_eur"),
                     "note": (pr.offer or {}).get("note"), "reliability": sc["reliability"], "measured": sc["measured"],
                     "invoice_ok": sc["invoice_ok"], "complaints": sc["complaints"],
                     "waiting_days": (utcnow() - pr.sent_at).days if pr.sent_at and pr.status in ("waiting", "chased") else None})
    rows.sort(key=lambda r: (r["status"] != "answered", r["available"] is not True, r["price_eur"] or 1e9, -r["reliability"]))
    return rows


def simulate_replies(s: Session, seed: int = 1) -> int:
    """Sandbox only: partners answer based on how quick and reliable they are, so the board moves."""
    rng = random.Random(seed)
    n = 0
    for pr in s.scalars(select(PartnerRequest).where(PartnerRequest.status.in_(["waiting", "chased"]))).all():
        p = s.get(Partner, pr.partner_id)
        waited = (utcnow() - pr.sent_at).days if pr.sent_at else 0
        if waited >= p.avg_reply_days and rng.random() < p.reliability:
            pr.status = "answered"
            pr.answered_at = utcnow()
            pr.offer = {"price_eur": rng.choice([680, 790, 940, 1120, 1380]), "available": rng.random() < 0.85,
                        "note": rng.choice(["Family room available", "Two separate rooms only", "Breakfast included",
                                            "Free cancellation until 45 days before arrival"])}
            n += 1
    s.commit()
    return n


class PartnerReply(BaseModel):
    available: bool | None
    price_eur: float | None = None
    note: str = ""
    needs_person: bool = False


READ_INSTRUCTIONS = (
    "Read the partner's reply in CONTEXT.mail. Say whether what we asked is available (true, false or null if unclear), "
    "the total price in euro if given, and a one line note in English. Set needs_person when the reply asks a question "
    "or proposes something else."
)


def read_reply(s: Session, mail_id: str) -> dict:
    """A partner answered: record the offer on the right request so the back office can compare."""
    from ..db import Mail
    from ..identity import agent  # noqa: F811
    from ..toolserver import server
    me = agent("partner_desk")
    if s.get(Mail, mail_id).status == "done":
        return {"skipped": "already read"}
    with audit(s, "partner_desk", mail_id, "reply") as box:
        info = server.call(s, me, "partners.read_reply", mail_id=mail_id)
        out, _ = run_step(s, "partner_reply", PartnerReply, READ_INSTRUCTIONS, {"mail": info["mail"]})
        m = s.get(Mail, mail_id)
        if not info["partner_request_id"]:
            m.status = "needs_person"  # never dropped: the back office matches it on the board
            m.triage = (m.triage or {}) | {"partner_reading": {"available": out.available, "price_eur": out.price_eur, "note": out.note}}
            box["output"] = "reply not matched to a request: back office matches it"
            s.commit()
            return {"matched": False}
        m.status = "done"
        pr = s.get(PartnerRequest, info["partner_request_id"])
        # only a clear yes counts as confirmed; a question, a 'we will come back to you' or an alternative needs a person
        pr.status = "declined" if out.available is False else "answered" if out.available is True and not out.needs_person else "unclear"
        pr.answered_at = utcnow()
        pr.offer = {"available": out.available, "price_eur": out.price_eur, "note": out.note, "needs_person": out.needs_person,
                    "mail_id": mail_id}
        s.commit()
        if pr.status == "declined":
            from ..jobs import enqueue, pending
            if not pending(s, "alternatives", pr.request_id) and not s.scalars(select(Draft).where(
                    Draft.request_id == pr.request_id, Draft.kind == "alternatives", Draft.status == "draft")).first():
                enqueue(s, "alternatives", {"request_id": pr.request_id})  # the specialist gets options, not just a 'no'
                s.commit()
        box["output"] = f"{pr.status} {out.price_eur or ''}"
    return {"matched": True, "partner_request_id": pr.id, "status": pr.status}


def decide(s: Session, partner_request_id: int, available: bool, price_eur: float | None, by: str, note: str = "") -> PartnerRequest:
    """A person read an unclear answer and decides what it means."""
    from .. import auditchain
    pr = s.get(PartnerRequest, partner_request_id)
    pr.status = "answered" if available else "declined"
    pr.offer = (pr.offer or {}) | {"available": available, "price_eur": price_eur if price_eur is not None else (pr.offer or {}).get("price_eur"),
                                   "needs_person": False, "decided_by": by, "note": note or (pr.offer or {}).get("note", "")}
    pr.answered_at = pr.answered_at or utcnow()
    auditchain.append(s, by, "partner_answer_decided", "partner_request", pr.id, ref="available" if available else "not available")
    s.commit()
    if not available:
        from ..jobs import enqueue
        enqueue(s, "alternatives", {"request_id": pr.request_id})
        s.commit()
    return pr


def silent_after_chase(s: Session, now=None) -> list[PartnerRequest]:
    """Chased and still silent: time to phone them or choose another partner."""
    now = now or utcnow()
    cutoff = now - timedelta(days=get_settings().chase_partner_after_days)
    return list(s.scalars(select(PartnerRequest).where(PartnerRequest.status == "chased", PartnerRequest.chased_at <= cutoff)).all())
