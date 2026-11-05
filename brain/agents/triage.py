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
from datetime import timedelta
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


EXTRA_LOAD = 3  # an expert may carry this many more open requests than the least busy colleague


def best_specialist(s: Session, team_id: str, destination: str | None) -> Employee | None:
    """Who should take this request: the colleague who knows the destination best, unless they are much busier.
    Knowing = trips there they brought to a booking (counts most), proposals they sent there, notes they own on it."""
    from ..db import Draft, KnowledgeItem
    people = s.scalars(select(Employee).where(Employee.team_id == team_id, Employee.role == "specialist",
                                              Employee.active.is_(True)).order_by(Employee.id)).all()
    if not people:
        return None
    load = {e.id: 0 for e in people}
    for tr in s.scalars(select(TripRequest).where(TripRequest.status.in_(["new", "proposal_draft", "proposal_sent", "change_requested"]),
                                                  TripRequest.specialist_id.in_(load))).all():
        load[tr.specialist_id] += 1
    floor = min(load.values())
    if not destination:
        return min(people, key=lambda e: (load[e.id], e.id))
    know = {e.id: 0.0 for e in people}
    for tr in s.scalars(select(TripRequest).where(TripRequest.destination == destination, TripRequest.specialist_id.in_(load))).all():
        know[tr.specialist_id] += 3.0 if tr.status == "booked" else 0.0
    for spec_id, n in s.execute(select(TripRequest.specialist_id, func.count()).join(Draft, Draft.request_id == TripRequest.id)
                                .where(Draft.kind == "proposal", Draft.status == "approved", TripRequest.destination == destination,
                                       TripRequest.specialist_id.in_(know)).group_by(TripRequest.specialist_id)).all():
        know[spec_id] += float(n)
    for k in s.scalars(select(KnowledgeItem).where(KnowledgeItem.destination == destination, KnowledgeItem.status == "approved")).all():
        if k.owner_id in know:
            know[k.owner_id] += 2.0
    able = [e for e in people if load[e.id] <= floor + EXTRA_LOAD]
    return max(able, key=lambda e: (know[e.id], -load[e.id]))  # ties: the first by id, as before


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
        from ..knowledge.concepts import destination_in
        if res.destination and res.destination not in DESTINATIONS:
            # a real model often answers with the name ("Sri Lanka", "Bali") instead of our key: translate, never guess
            res.destination = destination_in(res.destination)
        if not res.destination and res.category in ("new_request", "question", "change", "complaint"):
            # Gemma left it empty on half the clean mail (run 2): when the mail names exactly one of our destinations,
            # take it; two or none stays empty, so routing never rests on a guess
            text = f"{mail['subject']} {mail['body']}"
            named = {k for k, d in DESTINATIONS.items()
                     if re.search(rf"\b({re.escape(d['nl'])}|{re.escape(d['name'])})\b", text, re.I)}
            if len(named) == 1:
                res.destination = named.pop()
            elif not named:
                res.destination = destination_in(text)  # a place we know (Bali is Indonesia), or nothing
        team = team_for(s, res.destination)
        out = res.model_dump() | {"team_id": team.id if team else None, "escalated": escalated}
        if not m.family_id and not m.partner_id:  # a partner writing from their own address or domain
            partner = resolve_partner(s, m.sender, m.body)
            if partner is not None:
                m.partner_id = partner.id
                out["partner_id"] = partner.id
        if m.partner_id and res.category in ("question", "new_request", "change", "complaint"):
            # a partner's mail is never a family request: whatever it looks like, it is their answer to us
            out["category"] = "partner_reply"
            res.category = "partner_reply"
        if not m.family_id and not m.partner_id:  # real mail carries an address, not a family: match it, or open a new relation
            fam, notes = resolve_family(s, m.sender, res, m.body, m.subject)  # stored address; the model sees the domain
            out.update(notes)
            if fam is not None:
                m.family_id = fam.id
                out["new_relation"] = fam.id.startswith("f-new-")
            elif res.category in ("new_request", "change", "complaint", "question"):
                out["unknown_sender"] = True  # a person links it to the right family, helped by the candidates
        if m.family_id and res.category in ("question", "other", "complaint", "change"):
            # A family on the road is never a normal question: whatever the model said, link the trip that is
            # running now, mark it urgent, and treat distress as a complaint so the reply and the team lead come first.
            now_trip = travelling_trip(s, m.family_id, m.received_at.date())
            if now_trip is not None:
                out.update(while_travelling=True, urgent=True, request_id=now_trip.id, team_id=now_trip.team_id,
                           specialist_id=now_trip.specialist_id)
                if res.category in ("question", "other") and DISTRESS.search(f"{mail['subject']} {mail['body']}"):
                    out["category"] = res.category = "complaint"
                    out["model_category"] = "question"
            elif res.category in ("question", "other") and asks_for_change(s, m.family_id, f"{mail['subject']} {mail['body']}"):
                # names a stop of their own proposal together with a change ("a night less in Bangkok"): that is a
                # change request, whatever the model said; otherwise it would get an answer instead of a new version
                out["model_category"] = res.category
                out["category"] = res.category = "change"
            elif res.category == "question" and not out.get("request_id"):
                open_trip = latest_open_trip(s, m.family_id)  # so the answer moves with the trip when it is reassigned
                if open_trip is not None:
                    out.update(request_id=open_trip.id, specialist_id=open_trip.specialist_id)
        if res.category == "new_request" and m.family_id and res.child_ages:
            from ..db import Family as _F
            from ..family import set_ages
            f0 = s.get(_F, m.family_id)
            if f0 is not None and len(res.child_ages) >= len(f0.child_ages or []):
                set_ages(f0, res.child_ages, m.received_at.date())  # what they tell us now is the newest truth
        if res.category == "new_request" and m.family_id and res.destination:
            spec = best_specialist(s, team.id, res.destination) if team else None
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
        if res.category == "question" and m.family_id:
            enqueue(s, "answer_question", {"mail_id": m.id})
        if res.category == "change" and out.get("request_id") and not out.get("ambiguous_trip"):
            enqueue(s, "change", {"mail_id": m.id})  # the new version is ready when the specialist looks
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


DISTRESS = re.compile(r"vliegveld|luchthaven|gestrand|niemand (neemt|is|komt)|is er niet|niet (opgehaald|gekomen|komen opdagen)|"
                      r"kwijt|gestolen|ziekenhuis|ongeluk|noodgeval|dringend|spoed|\bhelp\b|wat moeten we doen|!!|"
                      r"airport|stranded|stuck|nobody|emergency|hospital|accident|urgent|stolen|lost our", re.I)


def travelling_trip(s: Session, family_id: str, on) -> TripRequest | None:
    """The booked trip this family is on right now (departure up to the last day), if any."""
    for t in s.scalars(select(TripRequest).where(TripRequest.family_id == family_id, TripRequest.status == "booked",
                                                  TripRequest.depart_date.is_not(None))).all():
        if t.depart_date <= on <= t.depart_date + timedelta(days=(t.days or 21) + 1):
            return t
    return None


CHANGE_WORDS = re.compile(r"\b(nacht(en)?|dag(en)?|night|nights|days?)\s+(langer|korter|minder|extra|meer|erbij|longer|shorter|less|fewer|more)\b|"
                          r"\b(overslaan|eruit|schrappen|in plaats van|ruilen|omwisselen|toevoegen|skip|instead of|swap)\b", re.I)


def asks_for_change(s: Session, family_id: str, text: str) -> bool:
    from .change import latest_version
    if not CHANGE_WORDS.search(text):
        return False
    low = text.lower()
    for t in s.scalars(select(TripRequest).where(TripRequest.family_id == family_id,
                                                  TripRequest.status.in_(["proposal_sent", "change_requested"]))).all():
        v = latest_version(s, t.id)
        if v and any((r.get("stop") or "").lower() in low for r in (v.data or {}).get("route", []) if r.get("stop")):
            return True
    return False


def latest_open_trip(s: Session, family_id: str) -> TripRequest | None:
    order = {"change_requested": 0, "proposal_sent": 1, "proposal_draft": 2, "new": 3, "booked": 4}
    trips = [t for t in s.scalars(select(TripRequest).where(TripRequest.family_id == family_id)).all() if t.status in order]
    trips.sort(key=lambda t: (order[t.status], -t.created_at.timestamp()))
    return trips[0] if trips else None


def triage_inbox(s: Session, limit: int | None = None) -> list[dict]:
    ids = [m.id for m in s.scalars(select(Mail).where(Mail.status == "new").order_by(Mail.received_at)).all()]
    return [triage_mail(s, i) for i in ids[:limit]]


# Name from the sign-off ---------------------------------------------------------------------------------------
# Rule: never a wrong name. A family named after our own specialist, or after "Team Marketing", is worse than none.

REPLY_HEADER = re.compile(r"^\s*(>|_{8,}|op .{4,80} schreef|on .{4,80} wrote:|-{3,}\s*(oorspronkelijk|original|doorgestuurd|forwarded)"
                          r"|(van|from|verzonden|sent|aan|to|onderwerp|subject):\s)", re.I)
FOOTER = re.compile(r"^\s*(verstuurd (vanaf|met)|verzonden (vanaf|met)|sent from|get outlook|outlook voor)", re.I)
DISCLAIMER = re.compile(r"^\s*(disclaimer|dit (e-?mail)?bericht is (vertrouwelijk|uitsluitend)|this (e-?mail|message) is confidential)", re.I)
GREETING = re.compile(r"^\s*(?:(?:hoi|hallo|hi|hey)[!,.]*\s+)?(met\s+)?(vriendelijke|hartelijke|lieve|warme|beste|kind|best|warm|many)?\s*"
                      r"(groet(en|jes)?|regards|wishes|liefs|mvg|m\.v\.g\.?|gr\.?|best|cheers|thanks|thank you|bedankt|"
                      r"dank je wel|dank jullie wel|alvast bedankt|tot snel|tot gauw)\b"
                      r"(?:\s+(?:alvast|a lot|so much|van ons allemaal|van ons|uit \w+|vanuit \w+|en tot snel))?"
                      r"(?:\s*/\s*kind regards)?[,!.]*\s*", re.I)
PARTICLES = {"van", "de", "der", "den", "ter", "ten", "het", "'t", "in", "la", "le", "da", "di", "du", "el", "al", "op"}
NOT_A_NAME = {"team", "marketing", "sales", "afdeling", "gezin", "hele", "ons", "onze", "wij", "we", "papa", "mama", "opa",
              "oma", "uit", "from", "the", "kids", "kinderen", "iedereen", "allemaal", "bv", "b.v.", "nv", "holding",
              "travel", "reizen", "reisbureau", "reisgezelschap", "company", "group", "groep", "stichting",
              "vereniging", "zonnebloem", "x"}


def _not_a_name() -> set[str]:
    from ..tenant import tenant
    return NOT_A_NAME | set(tenant().name_words)


FAMILY = re.compile(r"^(?:de\s+|the\s+)?(?:familie|fam\.?|family)\s+(.+)$|^(?:the\s+)?(.+?)\s+family$", re.I)


def _first_name(tok: str) -> bool:
    from ..names import FIRST_NAMES
    parts = tok.lower().replace("\u00eb", "e").replace("\u00ef", "i").split("-")
    return all(p in FIRST_NAMES or p.replace("e", "\u00eb") in FIRST_NAMES for p in parts) or tok.lower() in FIRST_NAMES


def _person(text: str) -> tuple[str, str] | None:
    """'Jan van der Berg' -> (full, 'van der Berg'); 'Anouk en Pieter' -> (full, ''); not a person -> None."""
    toks = text.split()
    if not toks or len(toks) > 7 or any(t.lower().strip(".,") in _not_a_name() for t in toks):
        return None
    if all(t.isupper() or t.islower() for t in toks if t.isalpha()):  # MARIEKE VISSER, marieke: fix the case only if sure
        if not _first_name(toks[0]):
            return None
        toks = [t.lower() if t.lower() in PARTICLES else t[:1].upper() + t[1:].lower() for t in toks]
    # split couples: "Marieke en Johan Visser", "Daan & Iris de Wit"
    joiner = next((i for i, t in enumerate(toks) if t.lower() in ("en", "&", "and")), None)
    firsts, rest = ([toks[0]], toks[1:]) if joiner is None else (toks[:joiner] + [toks[joiner + 1]], toks[joiner + 2:])
    if joiner is not None and (joiner != 1 or len(toks) < 3):
        return None
    for f in firsts:
        initial = re.fullmatch(r"[A-Z]\.", f)
        if not (initial or (f[:1].isupper() and _first_name(f))):
            return None
    surname = []
    for t in rest:
        if t.lower() in PARTICLES:
            surname.append(t.lower() if t != "El" else t)  # "El Amrani" keeps its capital
        elif t[:1].isupper() and re.fullmatch(r"[A-Z][\w'\u00e0-\u00ff-]+", t):
            surname.append(t)
        else:
            return None
    if surname and surname[-1].lower() in PARTICLES:
        return None
    if firsts[0].endswith(".") and not surname:
        return None
    return " ".join(toks), " ".join(surname)


def name_from_sign_off(body: str | None) -> tuple[str, str]:
    """(contact name, surname) as a person would read them from how the mail is signed. ('', '') when unsure;
    ('', 'Jansen') for 'Groeten, familie Jansen'. Only the family's own text counts, never quoted history."""
    lines = []
    for ln in (body or "").splitlines():
        if REPLY_HEADER.match(ln):
            break  # everything below is quoted history: often signed by our own specialist
        if DISCLAIMER.match(ln):
            break  # a disclaimer ends the family's own text
        if not FOOTER.match(ln):
            lines.append(ln.rstrip())
    while lines and not lines[-1].strip():
        lines.pop()
    tail = lines[-12:]
    if _own_signature(tail[-4:]):
        return "", ""  # our own signature (a forward or a test mail)
    cand = None
    for i in range(len(tail) - 1, -1, -1):
        ln = tail[i].strip()
        m = GREETING.match(ln)
        if m and len(ln) - m.end() < 60:
            rest = ln[m.end():].strip()
            after = next((x.strip() for x in tail[i + 1:] if x.strip()), "")
            cand = rest or after
            break
        if ln in ("--", "-- "):
            cand = next((x.strip() for x in tail[i + 1:] if x.strip()), "")
            break
    if not cand:
        return "", ""
    cand = re.split(r"\s*[|,(]|\s+\+?\d[\d\s-]{6,}|\s+\S+@\S+|\s+(?:www\.|https?://)", cand)[0]
    cand = re.sub(r"[^\w\s'&.\u00c0-\u024f-]", "", cand).strip(" .!")
    cand = re.sub(r"\s+(xx+|x)$", "", cand, flags=re.I)  # kisses after the name
    fam = FAMILY.match(cand)
    if fam:
        sur = (fam.group(1) or fam.group(2) or "").strip()
        sur = re.sub(r"s$", "", sur) if fam.group(2) and sur.endswith("s") and " " not in sur else sur
        p = _surname_only(sur)
        return ("", p) if p else ("", "")
    got = _person(cand)
    return got if got else ("", "")


def _own_signature(lines: list[str]) -> bool:
    """The company's own name or domain in the last lines: a forward or a test mail signed by us."""
    from ..tenant import tenant
    t = tenant()
    marks = [t.short_name.lower()] + [d for d in t.own_domains]
    return any(m in ln.lower() for ln in lines for m in marks)


def _surname_only(text: str) -> str | None:
    toks = text.split()
    if not toks or len(toks) > 4 or any(t.lower() in _not_a_name() for t in toks):
        return None
    if not toks[-1][:1].isupper() or not all(t.lower() in PARTICLES or t[:1].isupper() for t in toks):
        return None
    return " ".join(t.lower() if t.lower() in PARTICLES else t for t in toks)




def own_domains() -> set[str]:
    from ..tenant import tenant
    return set(tenant().own_domains)

FWD_FROM = re.compile(r"^\s*(?:van|from)\s*:\s*(?:.*?<)?([\w.+'-]+@[\w-]+(?:\.[\w-]+)+)>?", re.I | re.M)


def normalise_address(addr: str | None) -> str:
    """'Marieke Visser <Marieke.Visser+reizen@Ziggo.nl>' -> 'marieke.visser@ziggo.nl'."""
    from email.utils import parseaddr
    a = parseaddr(addr or "")[1].strip().lower()
    if "@" not in a:
        return ""
    local, domain = a.rsplit("@", 1)
    return local.split("+", 1)[0] + "@" + domain


def original_sender(sender: str | None, body: str | None) -> str:
    """A colleague forwarding a family's mail: the family is the 'Van:' inside, not the colleague."""
    addr = normalise_address(sender)
    if addr.rsplit("@", 1)[-1] in own_domains():
        for m in FWD_FROM.finditer(body or ""):
            inner = normalise_address(m.group(1))
            if inner and inner.rsplit("@", 1)[-1] not in own_domains():
                return inner
    return addr


def families_for_address(s: Session, addr: str) -> list:
    from ..db import Family, FamilyAddress
    if not addr:
        return []
    fams = {f.id: f for f in s.scalars(select(Family).where(func.lower(Family.email) == addr)).all()}
    for fa in s.scalars(select(FamilyAddress).where(FamilyAddress.email == addr)).all():
        fams.setdefault(fa.family_id, s.get(Family, fa.family_id))
    if not fams:  # stored addresses may carry a +tag: look those up by pattern, not by reading every family
        local, domain = addr.rsplit("@", 1)
        for f in s.scalars(select(Family).where(func.lower(Family.email).like(f"{local}+%@{domain}"))).all():
            fams[f.id] = f
    return list(fams.values())


def suggest_families(s: Session, surname: str, subject: str, body: str) -> list[dict]:
    """Likely families for a mail from an unknown address, for a person to confirm. Never linked automatically:
    a booking number or a surname is easy to type, and the reply would go to that address."""
    from ..db import Family
    out: dict[str, dict] = {}
    from ..tenant import tenant
    pre = tenant().ref_re
    for ref in re.findall(rf"\b{pre}-?R?(\d{{3,}})\b", f"{subject} {body}", re.I):
        tr = s.get(TripRequest, f"r{int(ref):03d}")
        if tr:
            out.setdefault(tr.family_id, {"family_id": tr.family_id, "why": [], "request_id": tr.id})["why"].append(
                f"mentions booking {tenant().reference(f'r{int(ref):03d}')}")
    if surname:
        for f in s.scalars(select(Family).where(func.lower(Family.surname) == surname.lower(),
                                                ~Family.notes.like("Samengevoegd met %")).limit(5)).all():
            out.setdefault(f.id, {"family_id": f.id, "why": []})["why"].append(f"same surname ({surname})")
    return sorted(out.values(), key=lambda x: -len(x["why"]))[:5]


def resolve_partner(s: Session, sender: str | None, body: str | None = None):
    """A partner by exact address, or by their own domain when only one partner uses it (staff write from
    reservations@, accounts@, a person's address). Free mail domains never count: anyone can have one."""
    from ..anonymise import FREEMAIL
    from ..db import Partner
    addr = original_sender(sender, body)
    if not addr:
        return None
    partners = s.scalars(select(Partner)).all()
    exact = [p for p in partners if normalise_address(p.email) == addr]
    if len(exact) == 1:
        return exact[0]
    domain = addr.rsplit("@", 1)[1]
    if domain in FREEMAIL or domain in own_domains():
        return None
    same = [p for p in partners if normalise_address(p.email).rsplit("@", 1)[-1] == domain]
    return same[0] if len(same) == 1 else None


def resolve_family(s: Session, sender: str | None, res, body: str | None = None, subject: str = "") -> tuple:
    """Which family wrote this? Returns (family or None, notes). Exact address match only, including addresses
    a person linked before. A first enquiry from an unknown address opens a new relation for the specialist to
    check; anything else from an unknown address waits for a person, with suggestions."""
    from ..db import Family, next_number
    addr = original_sender(sender, body)
    notes: dict = {}
    if addr != normalise_address(sender):
        notes["forwarded_from"] = addr
    if not addr:
        return None, notes
    found = families_for_address(s, addr)
    if len(found) == 1:
        return found[0], notes
    name, surname = name_from_sign_off(body)
    if len(found) > 1:  # one address, several families (shared address, grandparents): do not guess
        notes["shared_address"] = True
        notes["candidates"] = [{"family_id": f.id, "why": ["writes from this address"]} for f in found]
        return None, notes
    sugg = suggest_families(s, surname, subject, body or "")
    if res.category != "new_request":
        notes["candidates"] = sugg
        return None, notes
    n = next_number(s, "new_relation")
    from ..family import birth_years
    fam = Family(id=f"f-new-{n:04d}", surname=surname, contact_name=name, email=addr, adults=res.adults or 2,
                 child_ages=list(res.child_ages or []), child_birth_years=birth_years(res.child_ages or []), synthetic=False,
                 notes="Nieuwe relatie uit een eerste mail: controleer en maak aan in TravelSpirit.")
    s.add(fam)
    s.flush()
    if sugg:
        notes["possible_duplicate_of"] = sugg  # e.g. the other parent already has a relation
    return fam, notes