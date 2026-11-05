"""What the brain is worth: the numbers behind the success fee, against a baseline the client measures.

Everything is counted from what actually happened (requests, drafts, approvals, partner answers). Minutes saved
are an estimate: drafts the brain made, times the minutes a person used to spend on that task (the baseline,
measured with the pilot group before go-live), minus the share the specialist rewrote. The baseline values are
editable and shown as assumptions until the client has measured them.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import utcnow
from .db import Draft, InvoiceCheck, KnowledgeGap, KnowledgeItem, Mail, PartnerRequest, Setting, TripRequest

# Minutes a person spends per task today. PLACEHOLDERS until the baseline measurement (open question Q30).
DEFAULT_BASELINE = {
    "measured": False,
    "hours_to_first_proposal": 48,
    "minutes": {"triage": 3, "proposal": 90, "change": 30, "followup": 10, "partner_request": 8, "partner_chase": 5,
                "extras": 15, "roadbook": 60, "answer": 15, "complaint_reply": 25, "alternatives": 30,
                "invoice": 10, "next_trip": 15, "trip_alert": 10},
}
BRAIN_KINDS = ("proposal", "change", "followup", "partner_request", "partner_chase", "extras", "roadbook", "answer",
               "complaint_reply", "alternatives", "next_trip", "trip_alert")
UNPROMPTED = ("followup", "partner_chase", "extras", "roadbook", "alternatives", "next_trip", "trip_alert", "answer")


def baseline(s: Session) -> dict:
    st = s.get(Setting, "value:baseline")
    b = (st.value if st else None) or {}
    return DEFAULT_BASELINE | b | {"minutes": DEFAULT_BASELINE["minutes"] | (b.get("minutes") or {})}


def set_baseline(s: Session, value: dict, by: str) -> dict:
    from . import auditchain
    cur = baseline(s)
    new = cur | {k: v for k, v in value.items() if k in ("hours_to_first_proposal", "measured")}
    new["minutes"] = cur["minutes"] | {k: float(v) for k, v in (value.get("minutes") or {}).items() if k in cur["minutes"]}
    s.merge(Setting(key="value:baseline", value=new))
    auditchain.append(s, by, "value_baseline_set", "setting", "value:baseline")
    s.commit()
    return new


def _pct(a, b):
    return round(100 * a / b, 1) if b else None


def _median(xs):
    xs = sorted(xs)
    return round(xs[len(xs) // 2], 2) if xs else None


def report(s: Session, days: int = 30, team: str | None = None) -> dict:
    since = utcnow() - timedelta(days=days)
    b = baseline(s)
    rq = select(TripRequest).where(TripRequest.created_at >= since)
    team_ids = select(TripRequest.id).where(TripRequest.team_id == team)
    dq = select(Draft).where(Draft.created_at >= since)
    pq = select(PartnerRequest).where(PartnerRequest.sent_at >= since)
    if team:
        rq, dq, pq = (rq.where(TripRequest.team_id == team), dq.where(Draft.request_id.in_(team_ids)),
                      pq.where(PartnerRequest.request_id.in_(team_ids)))
    reqs = s.scalars(rq).all()
    ids = {r.id for r in reqs}
    drafts = s.scalars(dq).all()

    first = {}
    for d in drafts:
        if d.kind == "proposal" and d.request_id in ids and (d.request_id not in first or d.created_at < first[d.request_id]):
            first[d.request_id] = d.created_at
    hours_first = [(first[r.id] - r.created_at).total_seconds() / 3600 for r in reqs if r.id in first and r.mail_id]
    sent = [r for r in reqs if r.proposal_sent_at]
    hours_sent = [(r.proposal_sent_at - r.created_at).total_seconds() / 3600 for r in sent]

    decided = [d for d in drafts if d.status in ("approved", "rejected")]
    approved = [d for d in decided if d.status == "approved"]
    per_kind = {}
    for k in BRAIN_KINDS:
        ks = [d for d in drafts if d.kind == k]
        ap = [d for d in ks if d.status == "approved"]
        per_kind[k] = {"drafted": len(ks), "sent": len(ap), "discarded": sum(d.status == "rejected" for d in ks),
                       "sent_unchanged_pct": _pct(sum((d.edit_share or 0) < 0.02 for d in ap), len(ap)),
                       "avg_rewrite_pct": round(100 * sum(d.edit_share or 0 for d in ap) / len(ap), 1) if ap else None,
                       "auto_sent": sum((d.decided_by or "").startswith("auto:") for d in ap)}

    saved = 0.0
    for k, row in per_kind.items():
        per = b["minutes"].get(k, 0)
        for d in [d for d in drafts if d.kind == k and d.status == "approved"]:
            saved += per * (1 - min(d.edit_share or 0, 1))
    triaged = [] if team else [m for m in s.scalars(select(Mail).where(Mail.received_at >= since)).all() if m.triage]
    saved += b["minutes"]["triage"] * len(triaged)
    cq = select(InvoiceCheck).where(InvoiceCheck.created_at >= since)
    checks = s.scalars(cq.where(InvoiceCheck.request_id.in_(team_ids)) if team else cq).all()
    saved += b["minutes"]["invoice"] * len(checks)

    prs = s.scalars(pq).all()
    answered = [p for p in prs if p.answered_at]
    booked = [r for r in sent if r.status == "booked"]
    return {
        "period_days": days, "team": team or "all", "baseline": b,
        "speed": {"requests": len(reqs), "median_hours_to_first_proposal_draft": _median(hours_first),
                  "median_hours_to_proposal_sent": _median(hours_sent),
                  "baseline_hours_to_first_proposal": b["hours_to_first_proposal"]},
        "quality": {"drafts_decided": len(decided), "sent_pct": _pct(len(approved), len(decided)),
                    "sent_unchanged_pct": _pct(sum((d.edit_share or 0) < 0.02 for d in approved), len(approved)),
                    "avg_rewrite_pct": round(100 * sum(d.edit_share or 0 for d in approved) / len(approved), 1) if approved else None,
                    "per_kind": per_kind},
        "unprompted": {"drafts": sum(per_kind[k]["drafted"] for k in UNPROMPTED),
                       "by_kind": {k: per_kind[k]["drafted"] for k in UNPROMPTED},
                       "followups_withdrawn": sum(d.kind == "followup" and d.status == "rejected" and d.decided_by == "brain" for d in drafts)},
        "back_office": {"partner_requests": len(prs), "answered_pct": _pct(len(answered), len(prs)),
                        "median_reply_days": _median([(p.answered_at - p.sent_at).total_seconds() / 86400 for p in answered]),
                        "invoices_checked": len(checks), "invoice_status": dict(Counter(c.status for c in checks))},
        "sales": {"proposals_sent": len(sent), "booked": len(booked), "booked_pct": _pct(len(booked), len(sent))},
        "knowledge": {"gaps_open": s.query(KnowledgeGap).filter(KnowledgeGap.status == "open").count(),
                      "gaps_answered": s.query(KnowledgeGap).filter(KnowledgeGap.status == "written").count(),
                      "learned_waiting": s.query(KnowledgeItem).filter(KnowledgeItem.source.like("learned:%"),
                                                                       KnowledgeItem.status == "proposed").count()},
        "minutes_saved_estimate": round(saved), "hours_saved_estimate": round(saved / 60, 1),
        "safety": {"mail_flagged": sum(m.status == "flagged" for m in triaged)},
    }


def to_csv(r: dict) -> str:
    rows = [("period_days", r["period_days"]), ("team", r["team"]), ("baseline_measured", r["baseline"]["measured"]),
            ("requests", r["speed"]["requests"]),
            ("median_hours_to_first_proposal_draft", r["speed"]["median_hours_to_first_proposal_draft"]),
            ("baseline_hours_to_first_proposal", r["speed"]["baseline_hours_to_first_proposal"]),
            ("median_hours_to_proposal_sent", r["speed"]["median_hours_to_proposal_sent"]),
            ("drafts_sent_pct", r["quality"]["sent_pct"]), ("sent_unchanged_pct", r["quality"]["sent_unchanged_pct"]),
            ("avg_rewrite_pct", r["quality"]["avg_rewrite_pct"]), ("unprompted_drafts", r["unprompted"]["drafts"]),
            ("partner_answered_pct", r["back_office"]["answered_pct"]), ("partner_median_reply_days", r["back_office"]["median_reply_days"]),
            ("invoices_checked", r["back_office"]["invoices_checked"]), ("booked_pct", r["sales"]["booked_pct"]),
            ("hours_saved_estimate", r["hours_saved_estimate"])]
    return "measure,value\n" + "\n".join(f"{k},{'' if v is None else v}" for k, v in rows) + "\n"
