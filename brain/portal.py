"""Partner portal: local agents (and hotels that like it) answer our request line by line, without an account.

Local agents in Asia and Africa get prices from hotels, drivers and guides around them, and the answer comes in
pieces over days: "transfer confirmed, still asking the hotel in Ella, the boat trip is full but here is
another". By mail that becomes a long thread nobody can read. Here every line has its own status, price, valid
until date and thread, and we accept an alternative in one click. Partners with an API (western suppliers)
get connectors later; this is for people.

Security: one link per partner request with a 32-byte random token. It travels in the mail we send the partner;
the portal finds the request by the token's hash. Valid until departure or 120 days, and revoked when the
request is closed or a new link is issued. The partner sees the reference, the route, the
dates and the party (adults and children's ages), never the family's name, address or mail. What they type is
data: it is checked for injection and never handed to a model as instructions.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import utcnow
from .db import Family, Partner, PartnerRequest, PortalLine, PortalLink, PortalMessage, TripRequest

STATUSES = ("open", "asking", "confirmed", "alternative", "not_available")
LINK_DAYS = 120
MAX_TEXT = 2000
MONTHS_EN = dict(zip(["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"],
                     ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_url() -> str:
    import os
    return os.getenv("BRAIN_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def issue_link(s: Session, pr: PartnerRequest) -> str:
    """A fresh link (an older one for the same request stops working). Returns the URL to put in the mail."""
    for old in s.scalars(select(PortalLink).where(PortalLink.partner_request_id == pr.id, PortalLink.revoked.is_(False))).all():
        old.revoked = True
    token = secrets.token_urlsafe(32)
    tr = s.get(TripRequest, pr.request_id)
    until = utcnow() + timedelta(days=LINK_DAYS)
    if tr and tr.depart_date and tr.depart_date > utcnow().date():
        until = min(until, datetime.combine(tr.depart_date, time()))  # once they travel, the link has done its job
    s.add(PortalLink(token_hash=_hash(token), partner_request_id=pr.id, expires_at=until))
    if not s.scalars(select(PortalLine).where(PortalLine.partner_request_id == pr.id)).first():
        for i, (label, detail) in enumerate(lines_for(s, pr)):
            s.add(PortalLine(partner_request_id=pr.id, position=i, label=label, detail=detail))
    s.commit()
    return f"{public_url()}/portal/{token}"


def lines_for(s: Session, pr: PartnerRequest) -> list[tuple[str, str]]:
    """What we ask this partner, in lines, from the latest version of the route."""
    from .agents.change import latest_version
    p = s.get(Partner, pr.partner_id)
    v = latest_version(s, pr.request_id)
    route = (v.data or {}).get("route", []) if v else []
    out: list[tuple[str, str]] = []
    night = 1
    for i, r in enumerate(route):
        nights = r.get("nights") or 1
        when = f"night {night}" if nights == 1 else f"nights {night} to {night + nights - 1}"
        if p.kind == "hotel":
            if r.get("hotel") == p.name:
                out.append((f"Room at {p.name}", f"{when}, {r['stop']}"))
        else:
            out.append(("Airport transfer to " + r["stop"] if i == 0 else f"Transfer {route[i - 1]['stop']} to {r['stop']}", when.split(" to ")[0]))
            for a in r.get("activities") or []:
                out.append((f"{a} ({r['stop']})", when))
        night += nights
    if p.kind != "hotel" and route:
        out.append((f"Transfer {route[-1]['stop']} to the airport", f"day {night}"))
    return out or [(pr.what, "")]


def open_link(s: Session, token: str) -> PortalLink | None:
    if not token or len(token) > 100:
        return None
    link = s.get(PortalLink, _hash(token))
    if link is None or link.revoked or link.expires_at < utcnow():
        return None
    pr = s.get(PartnerRequest, link.partner_request_id)
    if pr is None or pr.status == "declined" and (pr.offer or {}).get("closed"):
        return None
    link.last_used_at = utcnow()
    return link


def view(s: Session, link: PortalLink) -> dict:
    """What the partner sees: the reference, the route and the party. Never the family's name or contact."""
    pr = s.get(PartnerRequest, link.partner_request_id)
    tr = s.get(TripRequest, pr.request_id)
    fam = s.get(Family, tr.family_id)
    p = s.get(Partner, pr.partner_id)
    from .config import get_settings
    from .synth.world import DESTINATIONS
    lines = s.scalars(select(PortalLine).where(PortalLine.partner_request_id == pr.id).order_by(PortalLine.position)).all()
    msgs = s.scalars(select(PortalMessage).where(PortalMessage.partner_request_id == pr.id).order_by(PortalMessage.id)).all()
    s.commit()
    return {"reference": f"TN-{tr.id.upper()}", "partner": p.name, "what": pr.what,
            "trip": {"destination": DESTINATIONS[tr.destination]["name"], "month": MONTHS_EN.get(tr.depart_month, tr.depart_month), "days": tr.days,
                     "depart_date": tr.depart_date.isoformat() if tr.depart_date else None},
            "party": {"adults": fam.adults, "children_ages": list(fam.child_ages or [])},
            "answer_by": (pr.sent_at + timedelta(days=get_settings().chase_partner_after_days)).date().isoformat() if pr.sent_at else None,
            "link_valid_until": link.expires_at.date().isoformat(),
            "lines": [line_dict(x) for x in lines],
            "messages": [{"id": m.id, "line_id": m.line_id, "author": m.author, "name": m.author_name if m.author == "travelnauts" else p.name,
                          "text": m.text, "round": m.round, "at": m.created_at.isoformat()} for m in msgs]}


def line_dict(x: PortalLine) -> dict:
    return {"id": x.id, "label": x.label, "detail": x.detail, "status": x.status, "price_eur": x.price_eur,
            "valid_until": x.valid_until.isoformat() if x.valid_until else None, "alternative": x.alternative, "note": x.note,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None}


def _round(s: Session, pr_id: int) -> int:
    last = s.scalars(select(PortalMessage).where(PortalMessage.partner_request_id == pr_id).order_by(PortalMessage.id.desc())).first()
    return last.round if last else 1


def update_line(s: Session, link: PortalLink, line_id: int, status: str, price_eur: float | None = None,
                valid_until: date | None = None, note: str = "", alternative: dict | None = None) -> dict:
    from . import auditchain
    x = s.get(PortalLine, line_id)
    if x is None or x.partner_request_id != link.partner_request_id:
        raise KeyError(line_id)
    if status not in STATUSES:
        raise ValueError("Unknown status")
    if status == "confirmed" and price_eur is None:
        raise ValueError("A confirmed line needs a price")
    if status == "alternative" and not (alternative and alternative.get("label")):
        raise ValueError("Describe the alternative")
    if valid_until and valid_until < utcnow().date():
        raise ValueError("Valid until is in the past")
    if price_eur is not None and not (0 <= price_eur <= 1_000_000):
        raise ValueError("Price out of range")
    x.status, x.price_eur, x.valid_until = status, price_eur, valid_until
    x.note = (note or "")[:MAX_TEXT]
    x.alternative = None if status != "alternative" else {"label": str(alternative["label"])[:300],
                                                          "price_eur": alternative.get("price_eur"), "note": str(alternative.get("note") or "")[:500]}
    x.updated_at, x.updated_by = utcnow(), "partner"
    _flag_text(s, link.partner_request_id, f"{note} {(alternative or {}).get('label', '')} {(alternative or {}).get('note', '')}")
    auditchain.append(s, f"partner:{s.get(PartnerRequest, link.partner_request_id).partner_id}", "portal_line", "portal_line", x.id, ref=status)
    s.commit()
    refresh_request(s, link.partner_request_id)
    return line_dict(x)


def _flag_text(s: Session, pr_id: int, text: str) -> bool:
    from .guardrails import detect_injection
    if text.strip() and detect_injection(text)["flagged"]:
        pr = s.get(PartnerRequest, pr_id)
        pr.offer = (pr.offer or {}) | {"flagged": True, "needs_person": True}
        return True
    return False


def add_message(s: Session, pr_id: int, author: str, name: str, text: str, line_id: int | None = None) -> dict:
    from . import auditchain
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        raise ValueError("Empty message")
    if line_id is not None:
        x = s.get(PortalLine, line_id)
        if x is None or x.partner_request_id != pr_id:
            raise KeyError(line_id)
    rnd = _round(s, pr_id)
    last = s.scalars(select(PortalMessage).where(PortalMessage.partner_request_id == pr_id).order_by(PortalMessage.id.desc())).first()
    if last and last.author != author and author == "travelnauts":
        rnd += 1  # we answer what they said: a new round
    flagged = author == "partner" and _flag_text(s, pr_id, text)
    m = PortalMessage(partner_request_id=pr_id, line_id=line_id, author=author, author_name=name, text=text, round=rnd, flagged=flagged)
    s.add(m)
    if author == "partner":
        pr = s.get(PartnerRequest, pr_id)
        pr.offer = (pr.offer or {}) | {"portal_activity_at": utcnow().isoformat(), "needs_person": True}
        if pr.status in ("waiting", "chased", "answered"):
            pr.status = "unclear"  # a question from the partner: someone reads it
    s.flush()
    auditchain.append(s, author if author != "partner" else f"partner:{s.get(PartnerRequest, pr_id).partner_id}",
                      "portal_message", "partner_request", pr_id, content=text)
    s.commit()
    return {"id": m.id, "round": m.round, "flagged": m.flagged}


def accept_alternative(s: Session, pr_id: int, line_id: int, by: str, by_name: str) -> dict:
    from . import auditchain
    x = s.get(PortalLine, line_id)
    if x is None or x.partner_request_id != pr_id or x.status != "alternative" or not x.alternative:
        raise ValueError("No alternative to accept on this line")
    alt = x.alternative
    x.label, x.status, x.price_eur = alt["label"], "confirmed", alt.get("price_eur")
    x.note = (x.note + f"\nAlternative accepted by Travelnauts ({by_name}).").strip()
    x.alternative, x.updated_at, x.updated_by = None, utcnow(), by
    s.add(PortalMessage(partner_request_id=pr_id, line_id=x.id, author="travelnauts", author_name=by_name,
                        text=f"We accept the alternative: {alt['label']}. Please book it.", round=_round(s, pr_id) + 1))
    auditchain.append(s, by, "portal_accept_alternative", "portal_line", x.id, ref=str(alt.get("price_eur")))
    s.commit()
    refresh_request(s, pr_id)
    return line_dict(x)


def refresh_request(s: Session, pr_id: int) -> PartnerRequest:
    """The lines decide the partner request: what the board, the availability check and the booking check read."""
    pr = s.get(PartnerRequest, pr_id)
    lines = s.scalars(select(PortalLine).where(PortalLine.partner_request_id == pr_id)).all()
    if not lines:
        return pr
    st = [x.status for x in lines]
    prices = [x.price_eur for x in lines if x.status == "confirmed" and x.price_eur is not None]
    valid = [x.valid_until for x in lines if x.status == "confirmed" and x.valid_until]
    offer = (pr.offer or {}) | {"source": "portal", "lines_total": len(lines), "lines_confirmed": st.count("confirmed"),
                                "lines_open": st.count("open") + st.count("asking"), "alternatives": st.count("alternative"),
                                "not_available": st.count("not_available"),
                                "price_eur": round(sum(prices), 2) if prices else None,
                                "valid_until": min(valid).isoformat() if valid else None,
                                "portal_activity_at": utcnow().isoformat()}
    if all(x == "confirmed" for x in st):
        pr.status, offer["available"], offer["needs_person"] = "answered", True, bool(offer.get("flagged"))
        offer["note"] = f"All {len(lines)} lines confirmed in the portal"
        pr.answered_at = pr.answered_at or utcnow()
    elif "alternative" in st or "not_available" in st:
        pr.status, offer["available"], offer["needs_person"] = "unclear", None, True
        offer["note"] = f"{st.count('alternative')} alternative(s), {st.count('not_available')} not available: choose on the board"
        pr.answered_at = pr.answered_at or utcnow()
    else:
        offer["available"] = None
        offer["note"] = f"{st.count('confirmed')} of {len(lines)} confirmed, the partner is still working on it"
    pr.offer = offer
    s.commit()
    return pr


def thread_for_staff(s: Session, pr_id: int) -> dict:
    """The same view for the back office and the specialist, with the partner's flagged text marked."""
    pr = s.get(PartnerRequest, pr_id)
    lines = s.scalars(select(PortalLine).where(PortalLine.partner_request_id == pr_id).order_by(PortalLine.position)).all()
    msgs = s.scalars(select(PortalMessage).where(PortalMessage.partner_request_id == pr_id).order_by(PortalMessage.id)).all()
    link = s.scalars(select(PortalLink).where(PortalLink.partner_request_id == pr_id, PortalLink.revoked.is_(False))).first()
    return {"partner_request_id": pr_id, "status": pr.status, "offer": pr.offer, "has_link": bool(link),
            "link_valid_until": link.expires_at.date().isoformat() if link else None,
            "last_seen_by_partner": link.last_used_at.isoformat() if link and link.last_used_at else None,
            "lines": [line_dict(x) for x in lines],
            "messages": [{"id": m.id, "line_id": m.line_id, "author": m.author, "name": m.author_name, "text": m.text,
                          "round": m.round, "flagged": m.flagged, "at": m.created_at.isoformat()} for m in msgs]}


def close(s: Session, pr_id: int) -> None:
    for link in s.scalars(select(PortalLink).where(PortalLink.partner_request_id == pr_id)).all():
        link.revoked = True
    s.commit()
