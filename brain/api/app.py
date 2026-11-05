"""HTTP API and the screens. Every endpoint checks the caller's role (Entra ID app roles; in the sandbox a
sign-in picker). Screens: specialist, team lead, back office, maintenance and user management."""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .. import auditchain, autosend, db, jobs
from ..agents import followup, galileo, knowledge_desk, partner_desk, proposal, triage
from ..config import get_settings
from ..db import (AgentRun, AuditEntry, Draft, Employee, Family, Job, KnowledgeItem, Mail, ModelCall, Setting, ToolCall,
                  PartnerRequest, TripRequest, as_dict)
from ..identity import (ROLES, EntraConfig, Principal, auth_mode, from_employee, verify_entra_token)
from ..knowledge.store import KnowledgeBase
from ..router import daily_cap, spent_today
from ..synth.world import DESTINATIONS
from ..toolserver import server as toolserver
from ..workflow import BlockedByCheck, approve_draft, backoffice_overview, reject_draft, teamlead_overview
from ..clock import utcnow

STATIC = Path(__file__).parent / "static"
CUSTOMER_DRAFTS = {"proposal", "change", "followup", "answer", "trip_alert", "galileo", "alternatives", "extras",
                   "complaint_reply", "next_trip", "call_notes", "roadbook"}
MONEY_WORDS = ("terugbetal", "refund", "compensatie", "vergoed", "korting", "geld terug", "compensation", "discount")
PARTNER_DRAFTS = {"partner_request", "partner_chase"}
# drafts that put a trip on the specialist's "Waiting for you" list (proposals and changes do it through the status)
WAITS_FOR_SPECIALIST = ["trip_alert", "complaint_reply", "answer", "followup", "alternatives", "extras", "roadbook"]

import os as _os

_TEST = _os.getenv("BRAIN_ENV", "test") == "test"
# API documentation only in the test environment; in pilot and live it would map the attack surface for free.
app = FastAPI(title="Travelnauts company brain (sandbox)", version="0.3.0",
              docs_url="/docs" if _TEST else None, redoc_url=None, openapi_url="/openapi.json" if _TEST else None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def _startup() -> None:
    import os
    if os.getenv("BRAIN_ENV", "test") == "test":
        db.create_all()  # pilot and live get their schema only from migrations (brain migrate)
    with db.session() as s:
        db.assert_synthetic_only(s)


# Limits: request size, and agent actions per person per minute (per replica) -------------------------

import time as _time
from collections import defaultdict as _dd

from fastapi import Request
from fastapi.responses import JSONResponse

MAX_BODY = 1_000_000
PORTAL_FILE_MAX = 5_000_000  # a partner's PDF offer
SECURITY_HEADERS = {
    # Screens use inline scripts, so 'unsafe-inline' is needed; everything else is locked to this site, the
    # Microsoft login and the font and MSAL CDNs. Output is always escaped in the screens (tested for XSS).
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                               "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
                               "img-src 'self' data: blob:; connect-src 'self' https://login.microsoftonline.com; "
                               "frame-src https://login.microsoftonline.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}
AGENT_ACTIONS_PER_MINUTE = 30
_buckets: dict = _dd(list)


@app.middleware("http")
async def limits(request: Request, call_next):
    size = int(request.headers.get("content-length") or 0)
    limit = PORTAL_FILE_MAX if request.url.path.startswith("/api/portal/") and request.url.path.endswith("/files") else MAX_BODY
    if size > limit:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    # NUL bytes have no business in a path, query or JSON body; Postgres refuses them, so stop them at the door
    if "\x00" in request.url.path or b"%00" in request.scope.get("query_string", b""):
        return JSONResponse({"detail": "Invalid characters in request"}, status_code=400)
    if request.method in ("POST", "PUT", "PATCH") and size:
        body = await request.body()
        if b"\x00" in body or b"\\u0000" in body:
            return JSONResponse({"detail": "Invalid characters in request"}, status_code=400)
    if request.method == "POST" and request.url.path.startswith("/api/") and not request.url.path.startswith("/api/admin"):
        who = request.headers.get("x-brain-user") or request.headers.get("authorization", "")[-24:] or request.client.host
        now_ = _time.time()
        _buckets[who] = [t for t in _buckets[who] if now_ - t < 60] + [now_]
        if len(_buckets[who]) > AGENT_ACTIONS_PER_MINUTE:
            return JSONResponse({"detail": "Too many actions in a minute, try again shortly"}, status_code=429)
    try:
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"  # customer data never sits in a browser or proxy cache
        return response
    except Exception as e:  # noqa: BLE001  never show a stack trace to a user
        import logging
        logging.getLogger("brain").exception("unhandled")
        return JSONResponse({"detail": f"Something went wrong ({type(e).__name__}). It is logged; try again or ask the admin."},
                            status_code=500)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


@app.get("/readyz", include_in_schema=False)
def readyz():
    from sqlalchemy import text
    try:
        with db.session() as s:
            s.execute(text("select 1"))
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": type(e).__name__}, status_code=503)


# Sign-in and roles ------------------------------------------------------------------------------

def current_user(x_brain_user: str | None = Header(None), authorization: str | None = Header(None)) -> Principal:
    with db.session() as s:
        if auth_mode() == "entra":
            if not authorization or not authorization.lower().startswith("bearer "):
                raise HTTPException(401, "Sign in with your Microsoft account")
            try:
                claims = verify_entra_token(authorization.split(" ", 1)[1], EntraConfig())
            except Exception as e:  # noqa: BLE001
                raise HTTPException(401, f"Invalid token: {type(e).__name__}")
            email = (claims.get("preferred_username") or claims.get("upn") or "").lower()
            e = s.scalars(select(Employee).where(func.lower(Employee.email) == email)).first()
            roles = {r for r in claims.get("roles", []) if r in ROLES}
            if e is None or not e.active or not roles:
                raise HTTPException(403, "No access. Ask your team lead to invite you.")
            p = Principal(id=e.id, name=e.name, roles=frozenset(roles), team_id=e.team_id)
        else:
            if not x_brain_user:
                raise HTTPException(401, "Pick who you are on the sign-in screen")
            e = s.get(Employee, x_brain_user)
            if e is None or not e.active:
                raise HTTPException(401, "Unknown or inactive user")
            p = from_employee(e)
        e.last_active = utcnow()
        s.commit()
        return p


def need(permission: str):
    def dep(user: Principal = Depends(current_user)) -> Principal:
        if not user.can(permission):
            raise HTTPException(403, f"Your role cannot do this ({permission})")
        return user
    return dep


def _request_visible(user: Principal, tr: TripRequest) -> bool:
    """Back office sees all trips, a team lead the team's, a specialist their own. Admins see no customer content."""
    if "back_office" in user.roles:
        return True
    if "team_lead" in user.roles:
        return tr.team_id == user.team_id
    return "specialist" in user.roles and tr.specialist_id == user.id


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/static/index.html")


@app.get("/api/auth-config")
def auth_config():
    """What the screens need to start a Microsoft sign-in (public values only)."""
    import os
    return {"mode": auth_mode(), "tenant_id": os.getenv("ENTRA_TENANT_ID", ""), "client_id": os.getenv("ENTRA_SPA_CLIENT_ID", ""),
            "api_scope": f"{os.getenv('ENTRA_CLIENT_ID', '')}/.default" if os.getenv("ENTRA_CLIENT_ID") else ""}


@app.get("/api/status")
def status():
    st = get_settings()
    with db.session() as s:
        return {"model": st.model, "triage_model": st.triage_model, "data_stage": st.data_stage,
                "travelspirit": st.travelspirit_mode, "travelspirit_write": st.travelspirit_write, "auth": auth_mode(),
                "families": s.query(Family).count(), "mails": s.query(Mail).count(),
                "knowledge": s.query(KnowledgeItem).count()}


@app.get("/api/signin-people")
def signin_people():
    """Sandbox only: the people you can sign in as."""
    if auth_mode() != "sandbox":
        raise HTTPException(404, "Use Microsoft sign-in")
    with db.session() as s:
        return [{"id": e.id, "name": e.name, "role": e.role, "team_id": e.team_id}
                for e in s.scalars(select(Employee).where(Employee.active.is_(True)).order_by(Employee.role, Employee.name)).all()]


@app.get("/api/me")
def me(user: Principal = Depends(current_user)):
    return {"id": user.id, "name": user.name, "roles": sorted(user.roles), "team_id": user.team_id,
            "can": sorted(p for p in __import__("brain.identity", fromlist=["PERMISSIONS"]).PERMISSIONS if user.can(p))}


# Inbox and requests -----------------------------------------------------------------------------

@app.get("/api/inbox")
def inbox(status: str | None = None, limit: int = 200, offset: int = 0, user: Principal = Depends(need("triage.run"))):
    with db.session() as s:
        q = select(Mail).order_by(Mail.received_at.desc()).limit(min(limit, 500)).offset(offset)
        if status:
            q = q.where(Mail.status == status)
        return [{k: v for k, v in as_dict(m).items() if k != "truth"} for m in s.scalars(q).all()]


@app.get("/api/mails/unlinked")
def unlinked_mail(user: Principal = Depends(need("mail.link"))):
    """Mail from an address we do not know, waiting for a person to say which family wrote it."""
    with db.session() as s:
        rows = s.scalars(select(Mail).where(Mail.family_id.is_(None), Mail.status == "triaged")
                         .order_by(Mail.received_at.desc()).limit(200)).all()
        out = []
        for m in rows:
            t = m.triage or {}
            if not t.get("unknown_sender"):
                continue
            if "team_lead" in user.roles and t.get("team_id") not in (None, user.team_id):
                continue
            cands = []
            for c in t.get("candidates", []):
                f = s.get(Family, c["family_id"])
                if f:
                    cands.append(c | {"name": f.contact_name or f"familie {f.surname}".strip()})
            out.append({"id": m.id, "received_at": m.received_at, "sender": m.sender, "subject": m.subject,
                        "category": t.get("category"), "summary": t.get("summary"), "shared_address": t.get("shared_address", False),
                        "candidates": cands})
        return out


class LinkMail(BaseModel):
    family_id: str
    remember_address: bool = True


@app.post("/api/mails/{mail_id}/link")
def link_mail(mail_id: str, body: LinkMail, user: Principal = Depends(need("mail.link"))):
    """A person says which family wrote this. The mail is triaged again with that family; the address is
    remembered for next time unless the person says it is a one-off (a shared or borrowed address)."""
    from ..agents.triage import original_sender
    from ..db import FamilyAddress
    with db.session() as s:
        m = s.get(Mail, mail_id) or _404("mail")
        f = s.get(Family, body.family_id) or _404("family")
        if m.family_id:
            raise HTTPException(400, "This mail is already linked")
        m.family_id, m.status = f.id, "new"
        addr = original_sender(m.sender, m.body)
        remembered = False
        if body.remember_address and addr and addr != (f.email or "").lower() and not s.get(FamilyAddress, addr):
            s.add(FamilyAddress(email=addr, family_id=f.id, added_by=user.id))
            remembered = True
        auditchain.append(s, user.id, "link_mail", "mail", mail_id, ref=f.id)
        s.commit()
        jobs.enqueue(s, "triage_mail", {"mail_id": mail_id})
        s.commit()
        return {"mail_id": mail_id, "family_id": f.id, "address_remembered": remembered}


@app.post("/api/triage")
def triage_all(limit: int | None = None, user: Principal = Depends(need("triage.run"))):
    with db.session() as s:
        return triage.triage_inbox(s, limit)


@app.get("/api/requests")
def requests(team: str | None = None, specialist: str | None = None, limit: int = 200, offset: int = 0,
             user: Principal = Depends(current_user)):
    with db.session() as s:
        q = select(TripRequest).order_by(TripRequest.created_at.desc()).limit(min(limit, 500)).offset(offset)
        if "back_office" in user.roles:
            pass
        elif "team_lead" in user.roles:
            q = q.where(TripRequest.team_id == user.team_id)
        elif "specialist" in user.roles:
            q = q.where(TripRequest.specialist_id == user.id)
        else:
            return []
        if team:
            q = q.where(TripRequest.team_id == team)
        if specialist:
            q = q.where(TripRequest.specialist_id == specialist)
        out = []
        pending: dict[str, list[str]] = {}
        for d in s.scalars(select(Draft).where(Draft.status == "draft", Draft.kind.in_(WAITS_FOR_SPECIALIST))).all():
            pending.setdefault(d.request_id, []).append(d.kind)
        for r in s.scalars(q).all():
            f = s.get(Family, r.family_id)
            out.append(as_dict(r) | {"family": f.contact_name, "child_ages": f.child_ages, "adults": f.adults,
                                      "destination_name": DESTINATIONS[r.destination]["name"], "pending": pending.get(r.id, [])})
        return out


def _visible_request(s, rid: str, user: Principal) -> TripRequest:
    r = s.get(TripRequest, rid)
    if r is None:
        _404("request")
    if not _request_visible(user, r):
        raise HTTPException(403, "Not your request")
    return r


@app.get("/api/requests/{rid}")
def request_detail(rid: str, user: Principal = Depends(current_user)):
    with db.session() as s:
        r = _visible_request(s, rid, user)
        f = s.get(Family, r.family_id)
        drafts = [as_dict(d) for d in s.scalars(select(Draft).where(Draft.request_id == rid).order_by(Draft.id)).all()]
        mail = s.get(Mail, r.mail_id) if r.mail_id else None
        return {"request": as_dict(r) | {"destination_name": DESTINATIONS[r.destination]["name"]}, "family": as_dict(f),
                "drafts": [d for d in drafts if d["kind"] in CUSTOMER_DRAFTS],
                "changes": [{k: v for k, v in as_dict(m).items() if k != "truth"} for m in s.scalars(
                    select(Mail).where(Mail.family_id == r.family_id).order_by(Mail.received_at)).all()
                    if (m.triage or {}).get("category") == "change" and (m.triage or {}).get("request_id") == rid],
                "mail": {k: v for k, v in as_dict(mail).items() if k != "truth"} if mail else None,
                "partners": partner_desk.compare_offers(s, rid),
                "availability": __import__("brain.workflow", fromlist=["availability"]).availability(s, rid)}


@app.post("/api/requests/{rid}/proposal")
def make_proposal(rid: str, user: Principal = Depends(current_user)):
    with db.session() as s:
        _visible_request(s, rid, user)
        return as_dict(proposal.write_proposal(s, rid))


@app.post("/api/mails/{mail_id}/change")
def apply_change(mail_id: str, user: Principal = Depends(current_user)):
    from ..agents.change import handle_change
    with db.session() as s:
        m = s.get(Mail, mail_id) or _404("mail")
        _visible_request(s, (m.triage or {}).get("request_id") or "", user)
        try:
            return as_dict(handle_change(s, mail_id))
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/requests/{rid}/galileo")
def make_galileo(rid: str, user: Principal = Depends(current_user)):
    with db.session() as s:
        _visible_request(s, rid, user)
        return as_dict(galileo.write_commands(s, rid))


@app.post("/api/requests/{rid}/partners")
def make_partner_requests(rid: str, user: Principal = Depends(current_user)):
    with db.session() as s:
        _visible_request(s, rid, user)
        try:
            return [as_dict(p) for p in partner_desk.plan_partner_requests(s, rid)]
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/requests/{rid}/alternatives")
def make_alternatives(rid: str, user: Principal = Depends(current_user)):
    from ..agents import sales
    with db.session() as s:
        _visible_request(s, rid, user)
        try:
            return as_dict(sales.alternatives(s, rid))
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/requests/{rid}/extras")
def make_extras(rid: str, user: Principal = Depends(current_user)):
    from ..agents import sales
    with db.session() as s:
        _visible_request(s, rid, user)
        try:
            return as_dict(sales.extras(s, rid))
        except ValueError as e:
            raise HTTPException(400, str(e))


class Notes(BaseModel):
    notes: str


@app.post("/api/requests/{rid}/call-notes")
def make_call_notes(rid: str, n: Notes, user: Principal = Depends(current_user)):
    from ..agents import sales
    with db.session() as s:
        _visible_request(s, rid, user)
        return as_dict(sales.call_notes(s, rid, n.notes))


@app.post("/api/requests/{rid}/roadbook")
def make_roadbook(rid: str, user: Principal = Depends(current_user)):
    from ..agents import backoffice as bo
    with db.session() as s:
        _visible_request(s, rid, user)
        try:
            return as_dict(bo.roadbook(s, rid))
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.get("/api/files/{kind}/{name}")
def get_file(kind: str, name: str, user: Principal = Depends(current_user)):
    """Roadbooks, vouchers and attachments, only for people who may see the trip."""
    from fastapi.responses import FileResponse
    from ..files import files_dir
    if kind not in ("roadbooks", "vouchers", "attachments") or "/" in name or ".." in name:
        _404("file")
    path = files_dir() / kind / name
    if not path.exists():
        _404("file")
    import re as _re
    ref = _re.search(r"(r\d{3,})", name.lower()) or _re.search(r"tn-(r\d{3,})", name.lower())
    with db.session() as s:
        if ref and not ("back_office" in user.roles):
            _visible_request(s, ref.group(1), user)
        elif not ref and "back_office" not in user.roles:
            raise HTTPException(403, "Not for your role")
    return FileResponse(path, media_type="application/pdf", filename=name)


@app.get("/api/invoices")
def invoice_checks(user: Principal = Depends(need("backoffice.board"))):
    from ..db import InvoiceCheck, Partner
    with db.session() as s:
        names = {p.id: p.name for p in s.scalars(select(Partner)).all()}
        return [as_dict(c) | {"partner": names.get(c.partner_id, "Unknown sender")}
                for c in s.scalars(select(InvoiceCheck).order_by(InvoiceCheck.resolved, InvoiceCheck.id.desc())).all()]


@app.post("/api/invoices/{cid}/resolve")
def resolve_invoice(cid: int, body: dict | None = None, user: Principal = Depends(need("backoffice.board"))):
    from ..db import InvoiceCheck
    with db.session() as s:
        c = s.get(InvoiceCheck, cid) or _404("invoice")
        why = str((body or {}).get("note", ""))[:300]
        if c.status in ("duplicate", "differs", "check") and not why:
            raise HTTPException(400, "Say how this was resolved (for example: credit note asked, not paid twice)")
        c.resolved = True
        if why:
            c.note = (c.note + " | Opgelost: " + why).strip(" |")
        auditchain.append(s, user.id, "invoice_resolved", "invoice", cid, ref=c.status, content=why or None)
        s.commit()
        return as_dict(c)


@app.get("/api/complaints")
def complaints(user: Principal = Depends(need("team.metrics"))):
    with db.session() as s:
        rows = s.scalars(select(Draft).where(Draft.kind == "complaint_reply").order_by(Draft.id.desc())).all()
        out = []
        for d in rows:
            m = s.get(Mail, (d.data or {}).get("mail_id"))
            if (d.data or {}).get("team_id") not in (None, user.team_id) and "admin" not in user.roles:
                continue
            out.append(as_dict(d) | {"mail": {"subject": m.subject, "body": m.body} if m else None})
        return out


class Reassign(BaseModel):
    specialist_id: str


@app.post("/api/requests/{rid}/reassign")
def reassign(rid: str, body: Reassign, user: Principal = Depends(need("requests.reassign"))):
    with db.session() as s:
        r = _visible_request(s, rid, user)
        e = s.get(Employee, body.specialist_id)
        if e is None or e.role != "specialist" or e.team_id != r.team_id:
            raise HTTPException(400, "Pick a specialist from the same team")
        r.specialist_id = e.id
        auditchain.append(s, user.id, "reassign", "request", rid, ref=e.id)
        s.commit()
        return as_dict(r)


@app.post("/api/partner-requests/{prid}/draft")
def draft_partner_request(prid: int, user: Principal = Depends(need("backoffice.board"))):
    with db.session() as s:
        return as_dict(partner_desk.draft_request_mail(s, prid))


# Jobs (in production these run on the scheduler) -------------------------------------------------

@app.post("/api/jobs/followups")
def job_followups(user: Principal = Depends(need("team.metrics"))):
    with db.session() as s:
        return [as_dict(d) for d in followup.run_followups(s)]


class MatchMail(BaseModel):
    partner_request_id: int


@app.post("/api/partner-mails/{mail_id}/match")
def match_partner_mail(mail_id: str, body: MatchMail, user: Principal = Depends(need("backoffice.board"))):
    """The back office says which request a partner mail answers; it is then read like any other reply."""
    from ..db import PartnerRequest
    with db.session() as s:
        m = s.get(Mail, mail_id) or _404("mail")
        pr = s.get(PartnerRequest, body.partner_request_id) or _404("partner request")
        if m.status != "needs_person":
            raise HTTPException(400, "This mail is already matched")
        m.triage = (m.triage or {}) | {"partner_request_id": pr.id}
        m.partner_id = m.partner_id or pr.partner_id
        m.status = "triaged"
        auditchain.append(s, user.id, "partner_mail_matched", "mail", mail_id, ref=str(pr.id))
        s.commit()
        jobs.enqueue(s, "partner_reply", {"mail_id": mail_id})
        s.commit()
        return {"mail_id": mail_id, "partner_request_id": pr.id}


class Decide(BaseModel):
    available: bool
    price_eur: float | None = None
    note: str = ""


@app.post("/api/partner-requests/{prid}/decide")
def decide_partner_answer(prid: int, body: Decide, user: Principal = Depends(need("backoffice.board"))):
    """An unclear partner answer, read by a person: available or not."""
    with db.session() as s:
        from ..db import PartnerRequest
        s.get(PartnerRequest, prid) or _404("partner request")
        return as_dict(partner_desk.decide(s, prid, body.available, body.price_eur, user.id, body.note))


@app.post("/api/jobs/chases")
def job_chases(user: Principal = Depends(need("backoffice.board"))):
    with db.session() as s:
        return [as_dict(partner_desk.draft_chase(s, p.id)) for p in partner_desk.due_chases(s)]


@app.post("/api/jobs/simulate-replies")
def job_simulate(user: Principal = Depends(need("backoffice.board"))):
    with db.session() as s:
        return {"answered": partner_desk.simulate_replies(s)}


@app.post("/api/jobs/run/{kind}")
def job_run(kind: str, user: Principal = Depends(need("jobs.run"))):
    if kind not in jobs.SCHEDULE:
        _404("job kind")
    with db.session() as s:
        j = jobs.enqueue(s, kind)
        s.commit()
        res = jobs.work(s)
        return next((r for r in res if r["id"] == j.id), {"id": j.id, "status": "queued"})


@app.post("/api/jobs/tick")
def job_tick(user: Principal = Depends(need("jobs.run"))):
    with db.session() as s:
        return {"scheduled": jobs.schedule_tick(s), "worked": jobs.work(s)}


# Drafts ------------------------------------------------------------------------------------------

class Decision(BaseModel):
    by: str | None = None
    final_body: str | None = None
    reason: str = ""


def _may_decide(s, user: Principal, d: Draft, final_text: str | None = None) -> None:
    if d.kind in PARTNER_DRAFTS:
        if not user.can("drafts.approve_partner"):
            raise HTTPException(403, "Partner mails are approved by the back office")
        return
    tr = s.get(TripRequest, d.request_id) if d.request_id else None
    owner = (d.data or {}).get("specialist_id") or (tr.specialist_id if tr else None)
    team = (d.data or {}).get("team_id") or (tr.team_id if tr else None)
    own = owner == user.id and user.can("drafts.approve_customer")
    exception = "team_lead" in user.roles and team == user.team_id
    if not (own or exception or (owner is None and team is None and user.can("drafts.approve_customer"))):
        raise HTTPException(403, "Only the specialist on this trip (or the team lead) approves customer mail")
    if d.kind == "complaint_reply" and "team_lead" not in user.roles:
        text = (final_text or d.body).lower()
        if any(w in text for w in MONEY_WORDS) or (d.data or {}).get("severity") == "high":
            raise HTTPException(403, "This reply talks about money or is high priority: the team lead approves it")


@app.get("/api/drafts")
def drafts(kind: str | None = None, status: str | None = "draft", limit: int = 300, offset: int = 0,
           user: Principal = Depends(current_user)):
    with db.session() as s:
        q = select(Draft).order_by(Draft.id.desc()).limit(min(limit, 1000)).offset(offset)
        if kind:
            q = q.where(Draft.kind.in_(kind.split(",")))
        if status:
            q = q.where(Draft.status == status)
        rows = s.scalars(q).all()
        if "back_office" in user.roles:
            pass
        elif "team_lead" in user.roles:
            team = {t.id for t in s.scalars(select(TripRequest).where(TripRequest.team_id == user.team_id)).all()}
            rows = [d for d in rows if d.request_id in team or (d.data or {}).get("team_id") == user.team_id]
        else:
            mine = {t.id for t in s.scalars(select(TripRequest).where(TripRequest.specialist_id == user.id)).all()}
            rows = [d for d in rows if (d.request_id in mine and not (d.data or {}).get("specialist_id"))
                    or (d.data or {}).get("specialist_id") == user.id]
        cache = {}
        return [as_dict(d) | {"auto_send_at": autosend.send_at(s, d, cache)} for d in rows]


@app.post("/api/drafts/{did}/approve")
def approve(did: int, d: Decision, user: Principal = Depends(current_user)):
    with db.session() as s:
        draft = s.get(Draft, did) or _404("draft")
        _may_decide(s, user, draft, d.final_body)
        try:
            out = as_dict(approve_draft(s, did, user.name, d.final_body, actor_id=user.id, team_lead="team_lead" in user.roles))
        except BlockedByCheck as e:
            raise HTTPException(422, f"Check failed: {e}")
        except ValueError as e:
            raise HTTPException(409, str(e))
        return out | {"ask_autosend": autosend.record(s, s.get(Draft, did), user.id, True)}


# Automatic send ------------------------------------------------------------------------------------------

@app.get("/api/autosend")
def autosend_mine(user: Principal = Depends(current_user)):
    """The person's automatic-send switches, any open question, and drafts counting down right now."""
    with db.session() as s:
        switches = autosend.mine(s, user.id, set(user.roles))
        counting = []
        if any(x["status"] == "on" for x in switches):
            cache, now = {}, utcnow()
            for d in s.scalars(select(Draft).where(Draft.status == "draft", Draft.kind.in_(autosend.ELIGIBLE),
                                                   Draft.created_at >= now - timedelta(hours=1))).all():
                at = autosend.send_at(s, d, cache)
                if not at:
                    continue
                try:
                    _may_decide(s, user, d)
                except HTTPException:
                    continue
                counting.append({"id": d.id, "kind": d.kind, "title": d.title, "send_at": at,
                                 "seconds_left": max(0, round((at - now).total_seconds(), 1))})
        return {"switches": switches, "counting": counting, "hold_seconds": autosend.hold_seconds()}


class AutoSendAnswer(BaseModel):
    choice: str


@app.post("/api/autosend/{kind}")
def autosend_answer(kind: str, body: AutoSendAnswer, user: Principal = Depends(current_user)):
    with db.session() as s:
        try:
            return autosend.answer(s, user.id, set(user.roles), kind, body.choice)
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))


@app.post("/api/drafts/{did}/stop")
def autosend_stop(did: int, user: Principal = Depends(current_user)):
    with db.session() as s:
        d = s.get(Draft, did) or _404("draft")
        _may_decide(s, user, d)
        try:
            return as_dict(autosend.stop(s, d, user.id))
        except ValueError as e:
            raise HTTPException(409, str(e))


@app.post("/api/drafts/{did}/send-due")
def autosend_due(did: int, user: Principal = Depends(current_user)):
    """The screen calls this when its countdown reaches zero, so the send does not wait for the next worker tick.
    It sends only what was due anyway; it can never send a draft early."""
    with db.session() as s:
        d = s.get(Draft, did) or _404("draft")
        _may_decide(s, user, d)
        at = autosend.send_at(s, d)
        if not at or at > utcnow():
            raise HTTPException(409, "Not due")
        sent = autosend.send(s, d)
        return {"sent": sent, "status": s.get(Draft, did).status, "blocked": (s.get(Draft, did).data or {}).get("auto_blocked")}


@app.post("/api/drafts/{did}/reject")
def reject(did: int, d: Decision, user: Principal = Depends(current_user)):
    with db.session() as s:
        draft = s.get(Draft, did) or _404("draft")
        _may_decide(s, user, draft)
        out = as_dict(reject_draft(s, did, user.name, d.reason, actor_id=user.id))
        autosend.record(s, s.get(Draft, did), user.id, False)
        return out


# Knowledge ---------------------------------------------------------------------------------------

class Question(BaseModel):
    question: str
    destination: str | None = None
    team_id: str | None = None


@app.post("/api/ask")
def ask(q: Question, user: Principal = Depends(need("knowledge.search"))):
    with db.session() as s:
        return knowledge_desk.ask(s, q.question, q.destination, q.team_id or user.team_id, role=sorted(user.roles)[0])


@app.get("/api/knowledge")
def knowledge(status: str | None = None, destination: str | None = None, user: Principal = Depends(current_user)):
    with db.session() as s:
        q = select(KnowledgeItem).order_by(KnowledgeItem.id)
        if status:
            q = q.where(KnowledgeItem.status == status)
        if destination:
            q = q.where(KnowledgeItem.destination == destination)
        owners = {e.id: e.name for e in s.scalars(select(Employee)).all()}
        return [as_dict(k) | {"owner": owners.get(k.owner_id)} for k in s.scalars(q).all()
                if user.roles & set(k.roles or [])]


class Approval(BaseModel):
    by: str | None = None


@app.post("/api/knowledge/{kid}/approve")
def approve_knowledge(kid: str, a: Approval, user: Principal = Depends(need("knowledge.approve"))):
    with db.session() as s:
        try:
            item = KnowledgeBase(s).approve(kid, user.name)
        except KeyError:
            _404("knowledge item")
        auditchain.append(s, user.id, "approve", "knowledge", kid, ref=f"v{item.version}", content=item.body)
        s.commit()
        return as_dict(item)


@app.post("/api/knowledge/reindex")
def knowledge_reindex(user: Principal = Depends(need("knowledge.approve"))):
    from ..knowledge.vault import reindex
    with db.session() as s:
        return reindex(s)


@app.get("/api/gaps")
def gaps(team: str | None = None, user: Principal = Depends(need("knowledge.search"))):
    with db.session() as s:
        return [as_dict(g) for g in KnowledgeBase(s).gaps(team)]


# Overviews, reports, metrics ---------------------------------------------------------------------

@app.get("/api/teamlead")
def teamlead(user: Principal = Depends(need("team.metrics"))):
    with db.session() as s:
        return teamlead_overview(s)


@app.get("/api/value")
def value_report(days: int = 30, team: str | None = None, user: Principal = Depends(need("team.metrics"))):
    """What the brain is worth, per period and team, against the baseline (estimates are labelled)."""
    from .. import value
    with db.session() as s:
        return value.report(s, max(1, min(days, 366)), team if team and team != "all" else None)


@app.get("/api/value.csv", response_class=PlainTextResponse)
def value_csv(days: int = 30, team: str | None = None, user: Principal = Depends(need("team.metrics"))):
    from .. import value
    with db.session() as s:
        return value.to_csv(value.report(s, max(1, min(days, 366)), team if team and team != "all" else None))


class BaselineIn(BaseModel):
    measured: bool | None = None
    hours_to_first_proposal: float | None = Field(None, ge=0, le=1000)
    minutes: dict[str, float] = {}


@app.post("/api/value/baseline")
def value_baseline(body: BaselineIn, user: Principal = Depends(need("team.metrics"))):
    from .. import value
    if any(v < 0 or v > 1000 for v in body.minutes.values()):
        raise HTTPException(400, "Minutes must be between 0 and 1000")
    with db.session() as s:
        return value.set_baseline(s, body.model_dump(exclude_none=True), user.id)


@app.get("/api/duplicates")
def duplicates_list(user: Principal = Depends(need("requests.reassign"))):
    from .. import duplicates
    with db.session() as s:
        return duplicates.candidates(s)


@app.get("/api/duplicates.csv", response_class=PlainTextResponse)
def duplicates_csv(user: Principal = Depends(need("requests.reassign"))):
    from .. import duplicates
    with db.session() as s:
        return duplicates.plan_csv(s)


class Pair(BaseModel):
    keep: str
    drop: str


@app.post("/api/duplicates/merge")
def duplicates_merge(p: Pair, user: Principal = Depends(need("requests.reassign"))):
    from .. import duplicates
    with db.session() as s:
        try:
            return duplicates.merge(s, p.keep, p.drop, user.id)
        except ValueError as e:
            raise HTTPException(409, str(e))


@app.post("/api/duplicates/apart")
def duplicates_apart(p: Pair, user: Principal = Depends(need("requests.reassign"))):
    from .. import duplicates
    with db.session() as s:
        duplicates.keep_apart(s, p.keep, p.drop, user.id)
        return {"ok": True}


# Partner portal ------------------------------------------------------------------------------------------
# The partner's side has no account: the token in the link is the key. Everything else stays behind sign-in.

def _portal(s, token: str):
    from .. import portal
    link = portal.open_link(s, token)
    if link is None:
        raise HTTPException(404, "This link is not valid (any more). Reply to our mail and we send a new one.")
    return link


@app.get("/portal/{token}", include_in_schema=False)
def portal_page(token: str):
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent / "static" / "portal.html", headers={"Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"})


@app.get("/api/portal/{token}")
def portal_view(token: str):
    from .. import portal
    with db.session() as s:
        return portal.view(s, _portal(s, token))


class PortalLineIn(BaseModel):
    status: str
    price_eur: float | None = None
    valid_until: date | None = None
    note: str = ""
    alternative: dict | None = None


@app.post("/api/portal/{token}/lines/{line_id}")
def portal_line(token: str, line_id: int, body: PortalLineIn):
    from .. import portal
    with db.session() as s:
        link = _portal(s, token)
        try:
            return portal.update_line(s, link, line_id, body.status, body.price_eur, body.valid_until, body.note, body.alternative)
        except KeyError:
            _404("line")
        except ValueError as e:
            raise HTTPException(400, str(e))


class PortalMsgIn(BaseModel):
    text: str
    line_id: int | None = None


@app.post("/api/portal/{token}/messages")
def portal_message(token: str, body: PortalMsgIn):
    from .. import portal
    with db.session() as s:
        link = _portal(s, token)
        try:
            return portal.add_message(s, link.partner_request_id, "partner", "", body.text, body.line_id)
        except KeyError:
            _404("line")
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/portal/{token}/files")
async def portal_file(token: str, request: Request):
    """A PDF offer or voucher. Only real PDFs, at most 5 MB; read later as data, like a mail attachment."""
    from .. import auditchain, portal
    from ..files import files_dir
    with db.session() as s:
        link = _portal(s, token)  # the token first: nothing about the upload is looked at without it
        data = await request.body()
        if not data.startswith(b"%PDF-") or len(data) > PORTAL_FILE_MAX:
            raise HTTPException(400, "Only PDF files up to 5 MB")
        pr = s.get(PartnerRequest, link.partner_request_id)
        name = f"portal-tn-{pr.request_id}-{pr.id}-{utcnow():%Y%m%d%H%M%S}.pdf"
        path = files_dir() / "attachments" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        portal.add_message(s, pr.id, "partner", "", f"Uploaded a PDF: {name}")
        auditchain.append(s, f"partner:{pr.partner_id}", "portal_file", "partner_request", pr.id, ref=name)
        s.commit()
        return {"file": name}


def _portal_staff(s, prid: int, user: Principal):
    pr = s.get(PartnerRequest, prid) or _404("partner request")
    if not user.can("backoffice.board"):
        _visible_request(s, pr.request_id, user)  # the trip's specialist (or their team lead) may follow it too
    return pr


@app.get("/api/partner-requests/{prid}/portal")
def portal_staff_view(prid: int, user: Principal = Depends(current_user)):
    from .. import portal
    with db.session() as s:
        _portal_staff(s, prid, user)
        return portal.thread_for_staff(s, prid)


@app.post("/api/partner-requests/{prid}/messages")
def portal_staff_message(prid: int, body: PortalMsgIn, user: Principal = Depends(current_user)):
    from .. import portal
    with db.session() as s:
        _portal_staff(s, prid, user)
        try:
            return portal.add_message(s, prid, "travelnauts", user.name, body.text, body.line_id)
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e))


@app.post("/api/partner-requests/{prid}/lines/{line_id}/accept")
def portal_accept(prid: int, line_id: int, user: Principal = Depends(current_user)):
    from .. import portal
    with db.session() as s:
        _portal_staff(s, prid, user)
        try:
            return portal.accept_alternative(s, prid, line_id, user.id, user.name)
        except ValueError as e:
            raise HTTPException(409, str(e))


@app.post("/api/partner-requests/{prid}/portal-link")
def portal_new_link(prid: int, user: Principal = Depends(need("backoffice.board"))):
    """A new link when the partner lost the mail; the old one stops working."""
    from .. import portal
    with db.session() as s:
        pr = s.get(PartnerRequest, prid) or _404("partner request")
        url = portal.issue_link(s, pr)
        auditchain.append(s, user.id, "portal_link_issued", "partner_request", prid)
        s.commit()
        return {"url": url}


@app.get("/api/backoffice")
def backoffice(user: Principal = Depends(need("backoffice.board"))):
    with db.session() as s:
        return backoffice_overview(s)


REPORT_ACCESS = {"supplier_watch": "backoffice.board", "booking_check": "backoffice.board", "customer_insight": "team.metrics", "team_insight": "team.metrics",
                 "review_reminders": "knowledge.approve"}


@app.get("/api/reports/{name}")
def report(name: str, user: Principal = Depends(current_user)):
    if name not in REPORT_ACCESS:
        _404("report")
    if not user.can(REPORT_ACCESS[name]):
        raise HTTPException(403, "Not for your role")
    with db.session() as s:
        st = s.get(Setting, f"report:{name}")
        return st.value if st else {"at": None}


@app.get("/api/metrics/teams.csv", response_class=PlainTextResponse)
def metrics_csv(user: Principal = Depends(need("team.metrics"))):
    """Team metrics for Power BI (per team, never per person)."""
    with db.session() as s:
        data = teamlead_overview(s)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "team", "open_requests", "proposals_drafted", "proposals_approved", "avg_edit_share",
                "avg_minutes_to_first_draft", "followups_due", "open_gaps"])
    for tid, t in data["teams"].items():
        w.writerow([utcnow().date().isoformat(), tid, t["open_requests"], t["proposals_drafted"],
                    t["proposals_approved"], t["avg_edit_share"], t["avg_minutes_to_first_draft"], t["followups_due"], len(t["gaps"])])
    return buf.getvalue()


@app.get("/api/employees")
def employees(user: Principal = Depends(current_user)):
    with db.session() as s:
        q = select(Employee).order_by(Employee.name)
        return [{"id": e.id, "name": e.name, "role": e.role, "team_id": e.team_id} for e in s.scalars(q).all() if e.active]


@app.get("/api/audit")
def audit_log(limit: int = 100, user: Principal = Depends(current_user)):
    with db.session() as s:
        q = select(AgentRun).order_by(AgentRun.id.desc()).limit(limit)
        rows = [as_dict(a) for a in s.scalars(q).all()]
        if not user.can("audit.read"):  # specialists see runs on their own trips only
            mine = {t.id for t in s.scalars(select(TripRequest).where(TripRequest.specialist_id == user.id)).all()}
            rows = [r for r in rows if r["subject"] in mine]
        return rows


@app.get("/api/traces/{trace_id}")
def trace(trace_id: str, user: Principal = Depends(need("audit.read"))):
    with db.session() as s:
        run = s.scalars(select(AgentRun).where(AgentRun.trace_id == trace_id)).first() or _404("trace")
        return {"run": as_dict(run),
                "tool_calls": [as_dict(t) for t in s.scalars(select(ToolCall).where(ToolCall.trace_id == trace_id)).all()],
                "model_calls": [as_dict(m) for m in s.scalars(select(ModelCall).where(ModelCall.trace_id == trace_id)).all()]}


# Maintenance and user management -----------------------------------------------------------------

AGENT_NAMES = ["triage", "proposal_writer", "change", "follow_up", "partner_desk", "galileo_helper", "knowledge_desk",
               "supplier_watcher", "customer_insight", "team_insight", "trip_monitor", "alternatives", "complaints",
               "next_trip", "extras", "call_notes", "invoice_matcher", "roadbook", "booking_check"]


@app.get("/api/admin/health")
def health(user: Principal = Depends(need("maintenance"))):
    from datetime import timedelta
    with db.session() as s:
        since = utcnow() - timedelta(hours=24)
        st = get_settings()
        paused = {a: bool((s.get(Setting, f"paused:{a}") or Setting(key="", value=False)).value) for a in AGENT_NAMES}
        runs = s.scalars(select(AgentRun).where(AgentRun.created_at >= since)).all()
        per_agent = {a: {"runs": 0, "errors": 0, "avg_ms": 0, "paused": paused[a]} for a in AGENT_NAMES}
        for r in runs:
            pa = per_agent.setdefault(r.agent, {"runs": 0, "errors": 0, "avg_ms": 0, "paused": False})
            pa["runs"] += 1
            pa["errors"] += not r.ok
            pa["avg_ms"] += r.ms
        for pa in per_agent.values():
            pa["avg_ms"] = round(pa["avg_ms"] / pa["runs"]) if pa["runs"] else 0
        tc = s.scalars(select(ToolCall).where(ToolCall.created_at >= since)).all()
        mc = s.scalars(select(ModelCall).where(ModelCall.created_at >= since)).all()
        stuck = s.scalars(select(Job).where(Job.status.in_(["queued", "running"]),
                                            Job.created_at < utcnow() - timedelta(hours=1))).all()
        bench = Path(__file__).resolve().parents[2] / "data" / "bench" / "report.json"
        return {
            "connections": [
                {"name": "TravelSpirit", "mode": st.travelspirit_mode, "ok": True, "detail": f"write: {st.travelspirit_write}"},
                {"name": "Models", "mode": st.model, "ok": all(m.ok for m in mc[-20:]) if mc else True,
                 "detail": f"{len(mc)} calls, {sum(not m.ok for m in mc)} failed, {sum(m.escalated for m in mc)} escalated, "
                           f"{sum(m.fallback_from is not None for m in mc)} fallbacks"},
                {"name": "Knowledge index", "mode": "vault", "ok": True,
                 "detail": f"last reindex {(s.get(Setting, 'last_reindex') or Setting(key='', value='never')).value}"},
                {"name": "Flight data", "mode": "stand-in", "ok": True, "detail": "flight number and date only"},
            ],
            "agents": per_agent,
            "tools": {"calls": len(tc), "denied": sum(not t.allowed for t in tc), "errors": sum(not t.ok for t in tc),
                      "cache_hits": sum(t.cached for t in tc)},
            "queue": {k: s.query(Job).filter(Job.status == k).count() for k in ("queued", "running", "done", "failed")},
            "stuck_jobs": [{"id": j.id, "kind": j.kind, "status": j.status, "error": j.error} for j in stuck[:10]],
            "failed_jobs": [{"id": j.id, "kind": j.kind, "error": j.error}
                            for j in s.scalars(select(Job).where(Job.status == "failed").order_by(Job.id.desc()).limit(10)).all()],
            "budget": {"spent_today_eur": round(spent_today(s), 4), "cap_eur": daily_cap(s)},
            "audit_chain": auditchain.verify_recent(s) | {"last_full_check": (s.get(Setting, "audit_full_check") or
                                                                              Setting(key="", value={})).value},
            "evals": __import__("json").loads(bench.read_text()) if bench.exists() else None,
            "release": {"version": app.version, "data_stage": st.data_stage},
        }


class Pause(BaseModel):
    paused: bool


@app.post("/api/admin/agents/{name}/pause")
def pause_agent(name: str, p: Pause, user: Principal = Depends(need("maintenance"))):
    if name not in AGENT_NAMES:
        _404("agent")
    with db.session() as s:
        s.merge(Setting(key=f"paused:{name}", value=p.paused))
        auditchain.append(s, user.id, "pause" if p.paused else "resume", "agent", name)
        s.commit()
        return {"agent": name, "paused": p.paused}


class Budget(BaseModel):
    cap_eur: float


@app.post("/api/admin/budget")
def set_budget(b: Budget, user: Principal = Depends(need("maintenance"))):
    with db.session() as s:
        s.merge(Setting(key="budget_cap_eur", value=b.cap_eur))
        auditchain.append(s, user.id, "budget", "setting", "budget_cap_eur", ref=str(b.cap_eur))
        s.commit()
        return {"cap_eur": b.cap_eur}


@app.get("/api/admin/alerts")
def open_alerts(user: Principal = Depends(need("maintenance"))):
    from ..alerts import as_json, checks
    with db.session() as s:
        return as_json(checks(s))


@app.post("/api/admin/jobs/retry-failed")
def retry_all_failed(user: Principal = Depends(need("maintenance"))):
    """After an outage: put every failed job back in the queue in one go. Logged in the audit chain."""
    from sqlalchemy import update
    with db.session() as s:
        n = s.execute(update(Job).where(Job.status == "failed")
                      .values(status="queued", attempts=0, error=None, run_after=utcnow())).rowcount
        auditchain.append(s, user.id, "retry_failed_jobs", "job", "all", ref=str(n))
        s.commit()
        return {"requeued": n}


@app.post("/api/admin/jobs/{jid}/retry")
def retry_job(jid: int, user: Principal = Depends(need("maintenance"))):
    with db.session() as s:
        j = s.get(Job, jid) or _404("job")
        j.status, j.attempts, j.error, j.run_after = "queued", 0, None, utcnow()
        s.commit()
        return as_dict(j)


@app.get("/api/admin/tools")
def tools(user: Principal = Depends(need("maintenance"))):
    return toolserver.describe()


@app.get("/api/admin/audit-chain")
def audit_chain(limit: int = 50, user: Principal = Depends(need("audit.read"))):
    with db.session() as s:
        return {"verify": auditchain.verify(s),
                "entries": [as_dict(e) for e in s.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)).all()]}


class BreakGlass(BaseModel):
    reason: str


@app.post("/api/admin/break-glass/mail/{mail_id}")
def break_glass(mail_id: str, b: BreakGlass, user: Principal = Depends(need("content.break_glass"))):
    """Admins do not see customer content by default. Opening it is logged in the audit chain with a reason."""
    if len(b.reason.strip()) < 10:
        raise HTTPException(400, "Give a reason of at least 10 characters")
    with db.session() as s:
        m = s.get(Mail, mail_id) or _404("mail")
        auditchain.append(s, user.id, "break_glass", "mail", mail_id, ref=b.reason[:120])
        s.commit()
        return {k: v for k, v in as_dict(m).items() if k != "truth"}


@app.get("/api/admin/users")
def users(user: Principal = Depends(need("users.manage"))):
    with db.session() as s:
        q = select(Employee).order_by(Employee.role, Employee.name)
        rows = s.scalars(q).all()
        if "admin" not in user.roles:  # team leads manage their own team
            rows = [e for e in rows if e.team_id == user.team_id]
        nxt = s.get(Setting, "next_access_review")
        return {"users": [{"id": e.id, "name": e.name, "email": e.email, "role": e.role, "team_id": e.team_id,
                           "active": e.active, "last_active": e.last_active} for e in rows],
                "roles": ROLES, "next_access_review": nxt.value if nxt else "2027-01-15"}


class Invite(BaseModel):
    name: str
    email: str
    role: str
    team_id: str | None = None


@app.post("/api/admin/users")
def invite(i: Invite, user: Principal = Depends(need("users.manage"))):
    if i.role not in ROLES:
        raise HTTPException(400, "Unknown role")
    if "admin" not in user.roles and (i.role in ("admin", "content") or i.team_id != user.team_id):
        raise HTTPException(403, "Team leads invite people into their own team only")
    from ..synth.generate import slug
    with db.session() as s:
        eid = slug(i.name)
        if s.get(Employee, eid):
            raise HTTPException(409, "Already exists")
        e = Employee(id=eid, name=i.name, email=i.email.lower(), role=i.role, team_id=i.team_id, active=True, synthetic=True)
        s.add(e)
        auditchain.append(s, user.id, "invite", "user", eid, ref=i.role)
        s.commit()
        return {"id": eid}


class RoleChange(BaseModel):
    role: str | None = None
    active: bool | None = None


@app.post("/api/admin/users/{eid}")
def change_user(eid: str, c: RoleChange, user: Principal = Depends(need("users.manage"))):
    with db.session() as s:
        e = s.get(Employee, eid) or _404("user")
        if "admin" not in user.roles and (e.team_id != user.team_id or c.role in ("admin", "content")):
            raise HTTPException(403, "Team leads manage their own team only")
        if eid == user.id and c.active is False:
            raise HTTPException(400, "You cannot remove yourself")
        if c.role:
            if c.role not in ROLES:
                raise HTTPException(400, "Unknown role")
            auditchain.append(s, user.id, "role_change", "user", eid, ref=f"{e.role}->{c.role}")
            e.role = c.role
        open_reqs = []
        if c.active is not None:
            auditchain.append(s, user.id, "access_removed" if not c.active else "access_restored", "user", eid)
            e.active = c.active
            if not c.active:  # what they leave behind must get a new owner
                open_reqs = [t.id for t in s.scalars(select(TripRequest).where(TripRequest.specialist_id == eid, TripRequest.status.in_(
                    ["new", "proposal_draft", "proposal_sent", "change_requested"]))).all()]
                from .. import jobs as _jobs
                _jobs.enqueue(s, "team_insight")
        s.commit()
        return {"id": eid, "role": e.role, "active": e.active, "open_requests_to_reassign": open_reqs}


@app.post("/api/reset")
def reset(seed: int | None = None, user: Principal = Depends(need("sandbox.reset"))):
    from ..synth.generate import build
    return build(seed or get_settings().seed)
