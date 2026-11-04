"""What partners actually do, measured every night from our own records (replaces the guesses we start with).

reply_days     average days from our request to their answer
reply_rate     share of requests they answered at all (silent after a reminder counts as no answer)
yes_rate       share of answers that said available
invoice_ok     share of their invoices that matched the agreed offer
complaints     complaints on trips where they were a hotel on the route
Used once there are at least MIN_SAMPLE requests; until then the starting values stay."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import utcnow
from .db import Draft, InvoiceCheck, Partner, PartnerRequest

MIN_SAMPLE = 3


def measure(s: Session) -> dict:
    now = utcnow()
    complaints_by_hotel: dict[str, int] = {}
    for d in s.scalars(select(Draft).where(Draft.kind == "complaint_reply")).all():
        v = s.scalars(select(Draft).where(Draft.request_id == d.request_id, Draft.kind.in_(["proposal", "change"]),
                                          Draft.status == "approved").order_by(Draft.decided_at.desc())).first() if d.request_id else None
        for r in (v.data or {}).get("route", []) if v else []:
            complaints_by_hotel[r["hotel"]] = complaints_by_hotel.get(r["hotel"], 0) + 1
    updated = 0
    for p in s.scalars(select(Partner)).all():
        prs = [pr for pr in s.scalars(select(PartnerRequest).where(PartnerRequest.partner_id == p.id)).all() if pr.sent_at]
        done = [pr for pr in prs if pr.answered_at]
        silent = [pr for pr in prs if not pr.answered_at and pr.sent_at < now - timedelta(days=7)]
        decided = len(done) + len(silent)
        inv = s.scalars(select(InvoiceCheck).where(InvoiceCheck.partner_id == p.id)).all()
        m = {"requests": len(prs),
             "reply_days": round(sum((pr.answered_at - pr.sent_at).total_seconds() / 86400 for pr in done) / len(done), 1) if done else None,
             "reply_rate": round(len(done) / decided, 2) if decided else None,
             "yes_rate": round(sum(pr.status == "answered" for pr in done) / len(done), 2) if done else None,
             "invoices": len(inv), "invoice_ok": round(sum(c.status == "match" for c in inv) / len(inv), 2) if inv else None,
             "complaints": complaints_by_hotel.get(p.name, 0), "at": now.isoformat(timespec="minutes")}
        if m != {k: v for k, v in (p.measured or {}).items()}:
            p.measured = m
            updated += 1
    s.commit()
    return {"partners_measured": updated}


def scores(p: Partner) -> dict:
    """The numbers to use for a partner: measured when there is enough, else the starting values."""
    m = p.measured or {}
    enough = (m.get("requests") or 0) >= MIN_SAMPLE
    return {"avg_reply_days": m["reply_days"] if enough and m.get("reply_days") is not None else p.avg_reply_days,
            "reliability": m["reply_rate"] if enough and m.get("reply_rate") is not None else p.reliability,
            "invoice_ok": m.get("invoice_ok"), "complaints": m.get("complaints", 0), "measured": enough}
