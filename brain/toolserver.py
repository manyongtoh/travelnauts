"""The tool server: the single door to TravelSpirit, the calculation, the knowledge base and outside data.

Every call says who is calling (an agent's identity or a person), is checked against that caller's
rights, is logged (tool, caller, time, allowed or not, never the content), and may be served from the
exact cache. The cache rule from the architecture: anything with customer data is cached per caller only,
so it is never served to another specialist or customer.

The same tools are published over MCP in mcp_server.py, so agents (and later the app and website) can
reach them as an MCP server.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import CacheEntry, Family, Partner, PastProposal, ToolCall, TripRequest, as_dict
from .identity import AGENTS, Principal
from .trace import current_trace


@dataclass
class Tool:
    name: str
    fn: Callable[..., Any]
    access: str  # read | draft | text
    description: str
    cache_seconds: int = 0
    customer_data: bool = True


class ToolServer:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}

    def tool(self, name: str, access: str = "read", cache_seconds: int = 0, customer_data: bool = True):
        def deco(fn):
            self.tools[name] = Tool(name, fn, access, (fn.__doc__ or "").strip().split("\n")[0], cache_seconds, customer_data)
            return fn
        return deco

    def allowed(self, caller: Principal, name: str) -> bool:
        if caller.kind == "agent":
            return name in AGENTS.get(caller.id, set())
        # People reach tools only through the API, which checks their role first; reads only.
        return self.tools[name].access == "read" and bool(caller.roles)

    def call(self, s: Session, caller: Principal, name: str, **kwargs) -> Any:
        if name not in self.tools:
            raise KeyError(f"Unknown tool {name}")
        t = self.tools[name]
        ok = self.allowed(caller, name)
        log = ToolCall(trace_id=current_trace(), caller=caller.id, tool=name, allowed=ok,
                       args_summary=",".join(sorted(kwargs))[:200])
        t0 = time.perf_counter()
        try:
            if not ok:
                raise PermissionError(f"{caller.id} may not use {name}")
            key = None
            if t.cache_seconds:
                raw = json.dumps(kwargs, sort_keys=True, default=str)
                key = "exact:" + hashlib.sha256(f"{name}|{caller.id if t.customer_data else '*'}|{raw}".encode()).hexdigest()
                hit = s.get(CacheEntry, key)
                if hit and hit.expires_at > datetime.utcnow():
                    log.cached = True
                    return hit.value
            out = json.loads(json.dumps(t.fn(s, **kwargs), default=str))  # tools return plain JSON, like over MCP
            if key:
                s.merge(CacheEntry(key=key, kind="exact", value=out, expires_at=datetime.utcnow() + timedelta(seconds=t.cache_seconds)))
            return out
        except Exception as e:
            log.ok = False
            log.error = f"{type(e).__name__}: {e}"[:500]
            raise
        finally:
            log.ms = int((time.perf_counter() - t0) * 1000)
            s.add(log)
            s.flush()

    def describe(self) -> list[dict]:
        return [{"name": t.name, "access": t.access, "description": t.description,
                 "agents": sorted(a for a, tools in AGENTS.items() if t.name in tools)} for t in self.tools.values()]


server = ToolServer()


# TravelSpirit (through the connector) ----------------------------------------------------------

def _ts(s):
    from .travelspirit.client import get_travelspirit
    return get_travelspirit(s)


@server.tool("ts.read_mail", cache_seconds=300)
def read_mail(s: Session, mail_id: str) -> dict:
    """Read one mail from TravelSpirit Mail."""
    return _ts(s).mail(mail_id)


@server.tool("ts.read_relation", cache_seconds=300)
def read_relation(s: Session, family_id: str) -> dict:
    """Read a relation (family) from TravelSpirit."""
    return _ts(s).relation(family_id)


@server.tool("ts.read_trip", cache_seconds=60)
def read_trip(s: Session, request_id: str) -> dict:
    """Read a dossier (trip request)."""
    tr = s.get(TripRequest, request_id)
    if tr is None:
        raise KeyError(request_id)
    return as_dict(tr)


@server.tool("ts.list_trips")
def list_trips(s: Session, status: str | None = None, family_id: str | None = None) -> list[dict]:
    """List dossiers, optionally by status or family."""
    q = select(TripRequest)
    if status:
        q = q.where(TripRequest.status == status)
    if family_id:
        q = q.where(TripRequest.family_id == family_id)
    return [as_dict(t) for t in s.scalars(q.order_by(TripRequest.created_at.desc())).all()]


@server.tool("ts.draft_reisplan", access="draft")
def draft_reisplan(s: Session, request_id: str, plan: dict) -> dict:
    """Create a draft reisplan in the Visual Tour Builder (drafts only, never final)."""
    return _ts(s).draft_reisplan(request_id, plan)


# Knowledge and examples ------------------------------------------------------------------------

@server.tool("knowledge.search", customer_data=False)
def knowledge_search(s: Session, query: str, destination: str | None = None, k: int = 4, role: str | None = None) -> list[dict]:
    """Search approved knowledge; results carry source, owner and review date."""
    from .knowledge.store import KnowledgeBase
    return [h.cite() | {"body": h.body} for h in KnowledgeBase(s).search(query, destination, k, role=role)]


@server.tool("examples.search", cache_seconds=600, customer_data=False)
def examples_search(s: Session, destination: str, days: int, k: int = 3) -> list[dict]:
    """Earlier proposals like this one, booked ones first."""
    rows = list(s.scalars(select(PastProposal).where(PastProposal.destination == destination)).all())
    rows.sort(key=lambda p: (not p.booked, abs(p.days - days)))
    return [as_dict(p) for p in rows[:k]]


# Calculation -----------------------------------------------------------------------------------

@server.tool("calc.quote", customer_data=False)
def calc_quote(s: Session, destination: str, route: list[dict], adults: int, child_ages: list[int],
               excursions: list[str] | None = None, request_id: str | None = None) -> dict:
    """Price a route from the price tables; returns a versioned quote."""
    from .pricing import quote
    return quote(s, destination, route, adults, child_ages, excursions, request_id)


# Partners and outside data ----------------------------------------------------------------------

@server.tool("partners.list", cache_seconds=600, customer_data=False)
def partners_list(s: Session, destination: str | None = None) -> list[dict]:
    """Partners with contact, kind and reliability."""
    q = select(Partner)
    if destination:
        q = q.where(Partner.destination == destination)
    return [as_dict(p) for p in s.scalars(q).all()]


@server.tool("galileo.write_commands", access="text", customer_data=False)
def galileo_check(s: Session, commands: list[str]) -> dict:
    """Check Galileo commands against the allowed formats. Text only: nothing is executed."""
    from .agents.galileo import ALLOWED
    bad = [c for c in commands if not any(p.match(c) for p in ALLOWED)]
    return {"ok": not bad, "unknown_format": bad}


def family_of(s: Session, family_id: str) -> Family | None:
    return s.get(Family, family_id)


@server.tool("prices.read", customer_data=False)
def prices_read(s: Session, destination: str | None = None) -> list[dict]:
    """Price lines with cost and validity (the calculation's price tables)."""
    from .db import PriceItem
    q = select(PriceItem)
    if destination:
        q = q.where(PriceItem.destination == destination)
    return [as_dict(p) | {"valid_until": p.valid_until.isoformat() if p.valid_until else None} for p in s.scalars(q).all()]


@server.tool("partners.read_reply")
def partners_read_reply(s: Session, mail_id: str) -> dict:
    """Read a partner's reply mail and the request it answers (matched on the TN reference)."""
    import re as _re
    from .db import Mail, PartnerRequest
    m = s.get(Mail, mail_id)
    ref = _re.search(r"TN-(R\d{3})", f"{m.subject} {m.body}", _re.I)
    pr = None
    if ref:
        q = select(PartnerRequest).where(PartnerRequest.request_id == ref.group(1).lower())
        if m.partner_id:
            q = q.where(PartnerRequest.partner_id == m.partner_id)
        pr = s.scalars(q).first()
    from .files import pdf_text
    atts = [{"name": a["name"], "text": pdf_text(a["path"])[:4000]} for a in (m.attachments or []) if a.get("mime") == "application/pdf"]
    return {"mail": {"subject": m.subject, "body": m.body, "partner_id": m.partner_id, "attachments": atts},
            "partner_request_id": pr.id if pr else None, "request_id": pr.request_id if pr else None}


@server.tool("stats.requests", customer_data=False)
def stats_requests(s: Session) -> list[dict]:
    """Request totals for insight agents: no names, no mail text, no contact details."""
    from .db import Draft
    first = {}
    for d in s.scalars(select(Draft).where(Draft.kind == "proposal").order_by(Draft.id)).all():
        first.setdefault(d.request_id, d.created_at)
    out = []
    for t in s.scalars(select(TripRequest)).all():
        fd = first.get(t.id)
        out.append({"id": t.id, "team_id": t.team_id, "destination": t.destination, "days": t.days,
                    "depart_month": t.depart_month, "budget_eur": t.budget_eur, "wishes": t.wishes, "status": t.status,
                    "last_change": (t.last_customer_contact or t.created_at).isoformat(),
                    "hours_to_first_draft": round((fd - t.created_at).total_seconds() / 3600, 2) if fd and t.mail_id else None})
    return out


@server.tool("travel.flight_status", cache_seconds=600, customer_data=False)
def flight_status(s: Session, number: str, date: str) -> dict:
    """Flight status by flight number and date only (stand-in for the real flight data provider)."""
    import hashlib as _h
    n = int(_h.sha256(f"{number}{date}".encode()).hexdigest(), 16) % 100
    if n < 6:
        return {"number": number, "date": date, "status": "cancelled", "delay_minutes": 0}
    if n < 20:
        return {"number": number, "date": date, "status": "delayed", "delay_minutes": 30 + n * 7}
    return {"number": number, "date": date, "status": "on_time", "delay_minutes": 0}
