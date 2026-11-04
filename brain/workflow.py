"""What happens when a person approves or rejects a draft, and the overviews for team leads and
the back office. Team lead figures are per team, never per employee (agreed in the proposal)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from .agents.followup import due_followups
from .agents.partner_desk import due_chases, mark_sent
from .db import AgentRun, Draft, KnowledgeItem, Mail, Partner, PartnerRequest, Team, TripRequest
from .knowledge.store import KnowledgeBase
from .clock import utcnow

HEAVY_REWRITE = 0.5  # more than half changed: the brain was missing something


def edit_share(before: str, after: str) -> float:
    return round(1 - SequenceMatcher(None, before, after).ratio(), 3)


class BlockedByCheck(ValueError):
    pass


CUSTOMER_KINDS = {"followup", "extras", "next_trip", "complaint_reply", "trip_alert", "roadbook", "alternatives", "change_reply"}
MONEY = ("terugbetal", "refund", "compensatie", "vergoed", "korting", "geld terug", "compensation", "discount", "gratis", "for free")
BOOKED_CLAIM = re.compile(r"\b(boeking|reis)\s+(is\s+)?(nu\s+)?(definitief\s+)?bevestigd|\bbooking\s+(is\s+)?confirmed|"
                          r"\bwe\s+hebben\s+(jullie\s+reis\s+|alles\s+)?geboekt", re.I)


def promise_problems(s: Session, d: Draft, text: str, team_lead: bool = False) -> list[str]:
    """Customer mail other than proposals and changes (those have their own check). Whatever wrote the text, a
    model gone wrong or one led by an injection, it may not invent prices, promise money or claim a booking."""
    if d.kind not in CUSTOMER_KINDS:
        return []
    from .guardrails import _amounts, _walk
    allowed = [float(v) for k, v in _walk(d.data or {}) if isinstance(v, (int, float)) and not isinstance(v, bool)
               and k and ("eur" in k.lower() or "price" in k.lower())]
    tr = s.get(TripRequest, d.request_id) if d.request_id else None
    if tr:
        for p in s.scalars(select(Draft).where(Draft.request_id == tr.id, Draft.kind.in_(["proposal", "change"]),
                                               Draft.status == "approved")).all():
            allowed.append(float(((p.data or {}).get("price") or {}).get("sell_eur") or 0))
    problems = [f"Price {a} euro is not from the calculation or the offer" for a in _amounts(text)
                if all(abs(a - p) > 1 for p in allowed)]
    if not team_lead and any(w in text.lower() for w in MONEY) and d.kind != "complaint_reply":
        problems.append("Promises money or a discount: the team lead approves this")
    if BOOKED_CLAIM.search(text) and not (tr and tr.status == "booked"):
        problems.append("Says the trip is booked, but it is not booked")
    return problems


CAVEAT = "Let op: de beschikbaarheid van de accommodaties bevestigen we nog; tot dan is dit voorstel onder voorbehoud."
CAVEAT_WORDS = ("onder voorbehoud", "beschikbaarheid", "subject to availability")


def availability(s: Session, request_id: str) -> dict:
    """Where the partner checks for this request stand."""
    from .agents.partner_desk import current_requests
    prs = current_requests(s, request_id)
    no = [pr for pr in prs if pr.status == "declined" or (pr.status == "answered" and (pr.offer or {}).get("available") is False)]
    ok = [pr for pr in prs if pr.status == "answered" and (pr.offer or {}).get("available") is True]
    from .config import get_settings
    return {"asked": len(prs), "confirmed": len(ok), "not_available": len(no), "open": len(prs) - len(ok) - len(no),
            "rule": get_settings().availability_rule}


def availability_check(s: Session, d: Draft, text: str) -> tuple[list[str], str]:
    """For a proposal or change: problems that block it, and the text to send (with a caveat when needed)."""
    if d.kind not in ("proposal", "change") or not d.request_id:
        return [], text
    a = availability(s, d.request_id)
    if a["not_available"]:
        return [f"{a['not_available']} partner(s) said not available: choose an alternative before sending"], text
    if a["rule"] == "block" and (a["asked"] == 0 or a["open"]):
        return ["Wait until all partners confirm availability before sending this proposal"
                if a["asked"] else "Ask the partners for availability first (rule: wait for confirmation)"], text
    if a["rule"] == "warn" and (a["asked"] == 0 or a["open"]) and not any(w in text.lower() for w in CAVEAT_WORDS):
        return [], text.rstrip() + "\n\n" + CAVEAT
    return [], text


def approve_draft(s: Session, draft_id: int, by: str, final_body: str | None = None, actor_id: str | None = None,
                  team_lead: bool = False) -> Draft:
    from . import auditchain
    from .guardrails import check_output
    d = s.get(Draft, draft_id)
    if d is None:
        raise KeyError(draft_id)
    if d.status != "draft":
        raise ValueError(f"Draft {draft_id} is already {d.status}")
    text = final_body if final_body is not None else d.body
    stale = stale_reason(s, d)
    if stale:
        raise BlockedByCheck(stale)
    promises = promise_problems(s, d, text, team_lead)
    if promises:
        raise BlockedByCheck("; ".join(promises))
    avail, text = availability_check(s, d, text)
    if avail:
        raise BlockedByCheck("; ".join(avail))
    if d.kind in ("proposal", "change"):
        price = (d.data or {}).get("price") or {}
        allowed = [price.get("sell_eur")] + [((d.data or {}).get("price_before") or {}).get("sell_eur")]
        problems = [p for p in check_output(text, [a for a in allowed if a]) if "dashes" not in p]
        if problems:
            raise BlockedByCheck("; ".join(problems))
    d.final_body = text
    d.edit_share = edit_share(d.body, d.final_body)
    d.status = "approved"
    d.decided_at = utcnow()
    d.decided_by = by
    tr = s.get(TripRequest, d.request_id) if d.request_id else None
    if d.kind == "proposal" and tr:
        tr.status = "proposal_sent"
        tr.proposal_sent_at = d.decided_at
    if d.kind == "change" and tr:
        tr.status = "proposal_sent"
        tr.days = d.data.get("days_after", tr.days)
        tr.proposal_sent_at = d.decided_at
    if d.kind == "partner_request" and d.partner_request_id:
        mark_sent(s, d.partner_request_id, d.decided_at)
    auditchain.append(s, actor_id or by, "approve", f"draft:{d.kind}", d.id, ref=d.request_id, content=d.final_body)
    if d.edit_share > HEAVY_REWRITE and tr:
        KnowledgeBase(s).record_gap(f"{d.kind} voor {tr.destination} werd grotendeels herschreven ({d.title})",
                                    "heavy_rewrite", tr.destination, tr.team_id)
    s.commit()
    return d


def reject_draft(s: Session, draft_id: int, by: str, reason: str = "", actor_id: str | None = None) -> Draft:
    from . import auditchain
    d = s.get(Draft, draft_id)
    if d is None:
        raise KeyError(draft_id)
    auditchain.append(s, actor_id or by, "discard", f"draft:{d.kind}", d.id, ref=d.request_id, content=d.body)
    d.status = "rejected"
    d.decided_at = utcnow()
    d.decided_by = by
    d.data = (d.data or {}) | {"reject_reason": reason}
    s.commit()
    return d


def teamlead_overview(s: Session) -> dict:
    teams = {t.id: t.name for t in s.scalars(select(Team)).all()}
    reqs = list(s.scalars(select(TripRequest)).all())
    drafts = list(s.scalars(select(Draft)).all())
    by_req = defaultdict(list)
    for d in drafts:
        if d.request_id:
            by_req[d.request_id].append(d)
    kb = KnowledgeBase(s)
    out = {}
    for tid, name in teams.items():
        tr = [r for r in reqs if r.team_id == tid]
        props = [d for r in tr for d in by_req[r.id] if d.kind == "proposal"]
        decided = [d for d in props if d.status == "approved"]
        minutes = [(d.created_at - r.created_at).total_seconds() / 60 for r in tr for d in by_req[r.id]
                 if d.kind == "proposal" and r.mail_id]
        out[tid] = {
            "team": name,
            "open_requests": sum(r.status in ("new", "proposal_draft", "proposal_sent", "change_requested") for r in tr),
            "status": dict(Counter(r.status for r in tr)),
            "proposals_drafted": len(props),
            "proposals_approved": len(decided),
            "avg_edit_share": round(sum(d.edit_share for d in decided) / len(decided), 3) if decided else None,
            "avg_minutes_to_first_draft": round(sum(minutes) / len(minutes), 1) if minutes else None,
            "followups_waiting": [{"request_id": d.request_id, "title": d.title, "days_since": (d.data or {}).get("days_since")}
                                  for r in tr for d in by_req[r.id] if d.kind == "followup" and d.status == "draft"],
            "followups_due": sum(r.team_id == tid for r in due_followups(s)),
            "gaps": [{"id": g.id, "question": g.question, "reason": g.reason, "count": g.count} for g in kb.gaps(tid)],
        }
    due = kb.review_due()
    team_of = {dest: tid for tid, t in ((t.id, t) for t in s.scalars(select(Team)).all()) for dest in t.destinations}
    return {"teams": out, "review_due": [{"id": k.id, "title": k.title, "review_by": k.review_by.isoformat(),
                                          "owner": k.owner_id, "team_id": team_of.get(k.destination)} for k in due],
            "proposed_knowledge": [{"id": k.id, "title": k.title + (" (change)" if k.pending_body else ""), "owner": k.owner_id,
                                    "team_id": team_of.get(k.destination)} for k in
                                   s.scalars(select(KnowledgeItem).where((KnowledgeItem.status == "proposed") |
                                                                         (KnowledgeItem.pending_body.is_not(None)))).all()],
            "inbox": dict(Counter(m.status for m in s.scalars(select(Mail)).all())),
            "agent_runs_24h": s.query(AgentRun).filter(AgentRun.created_at >= utcnow() - timedelta(days=1)).count()}


def backoffice_overview(s: Session) -> dict:
    prs = list(s.scalars(select(PartnerRequest)).all())
    partners = {p.id: p for p in s.scalars(select(Partner)).all()}
    chase_ids = {p.id for p in due_chases(s)}
    from .agents.partner_desk import silent_after_chase
    silent_ids = {p.id for p in silent_after_chase(s)}
    from .db import Family
    from .synth.world import DESTINATIONS
    reqs = {r.id: r for r in s.scalars(select(TripRequest)).all()}
    pending = {d.partner_request_id: d.id for d in s.scalars(select(Draft).where(
        Draft.kind.in_(["partner_request", "partner_chase"]), Draft.status == "draft")).all()}
    cards = []
    for pr in prs:
        p = partners[pr.partner_id]
        tr = reqs.get(pr.request_id)
        fam = s.get(Family, tr.family_id) if tr else None
        cards.append({"id": pr.id, "request_id": pr.request_id, "partner": p.name, "partner_id": p.id, "kind": p.kind, "what": pr.what,
                      "destination": DESTINATIONS[tr.destination]["name"] if tr else None,
                      "team_id": tr.team_id if tr else None, "family": fam.surname if fam else None,
                      "draft_id": pending.get(pr.id),
                      "age_hours": int(((utcnow() - (pr.answered_at or pr.chased_at or pr.sent_at)).total_seconds()) // 3600)
                      if (pr.answered_at or pr.chased_at or pr.sent_at) else None,
                      "status": pr.status, "sent_at": pr.sent_at.isoformat() if pr.sent_at else None,
                      "waiting_days": (utcnow() - pr.sent_at).days if pr.sent_at and pr.status in ("waiting", "chased") else None,
                      "chase_due": pr.id in chase_ids, "silent_after_chase": pr.id in silent_ids, "offer": pr.offer})
    slow = sorted(({"partner": p.name, "kind": p.kind, "destination": DESTINATIONS.get(p.destination, {}).get("name", "All"),
                    "avg_reply_days": p.avg_reply_days, "reliability": p.reliability}
                   for p in partners.values() if p.kind != "airline"), key=lambda x: -x["avg_reply_days"])
    to_match = [{"mail_id": m.id, "from": m.sender, "subject": m.subject, "received_at": m.received_at.isoformat(),
                 "partner_id": m.partner_id, "reading": (m.triage or {}).get("partner_reading")}
                for m in s.scalars(select(Mail).where(Mail.status == "needs_person").order_by(Mail.received_at)).all()]
    return {"cards": cards, "counts": dict(Counter(c["status"] for c in cards)), "chase_due": len(chase_ids),
            "silent_after_chase": len(silent_ids), "partner_mail_to_match": to_match,
            "slowest_partners": slow,
            "drafts_to_check": s.query(Draft).filter(Draft.kind.in_(["partner_request", "partner_chase"]),
                                                     Draft.status == "draft").count()}


def stale_reason(s: Session, d: Draft) -> str | None:
    """A follow-up is only right while the family still has not answered our proposal."""
    if d.kind != "followup" or not d.request_id:
        return None
    tr = s.get(TripRequest, d.request_id)
    if tr is None:
        return None
    if tr.status != "proposal_sent":
        return f"No longer needed: the request is now {tr.status.replace('_', ' ')}."
    if tr.last_customer_contact and d.created_at and tr.last_customer_contact > d.created_at:
        return "No longer needed: the family wrote to us after this follow-up was drafted."
    return None


def withdraw_stale_drafts(s: Session) -> int:
    """Take back follow-ups that events overtook (booked, answered, lost), so nobody sends them by mistake."""
    n = 0
    for d in s.scalars(select(Draft).where(Draft.kind == "followup", Draft.status == "draft")).all():
        why = stale_reason(s, d)
        if why:
            reject_draft(s, d.id, "brain", reason=why)
            n += 1
    return n
