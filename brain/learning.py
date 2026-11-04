"""How the brain learns from daily work. Nothing it learns is used before a person approves it.

1. From edits: what specialists keep adding to or removing from drafts becomes a proposed house rule for the
   team lead (three or more drafts, two or more specialists, in 30 days). Approved rules go into the prompts.
2. From outcomes: every proposal a family booked or turned down becomes an example, as the specialist sent it,
   without names. The proposal writer is shown booked examples that look most like the new trip.
3. From answers: when the knowledge desk did not know and a specialist answered the family, that answer becomes a
   proposed knowledge note for the owner, and the gap is marked written.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import today as clock_today
from .clock import utcnow
from .db import Draft, Employee, Family, KnowledgeGap, KnowledgeItem, PastProposal, TripRequest

LEARN_FROM = ("proposal", "change", "followup", "extras", "answer", "next_trip")
MIN_DRAFTS, MIN_PEOPLE, WINDOW_DAYS = 3, 2, 30
GREETING_LINE = re.compile(r"^\s*(beste|hoi|hallo|dag|lieve|dear|hi|hello)\b", re.I)
SIGN_OFF_LINE = re.compile(r"^\s*(met\s+)?(vriendelijke|hartelijke|warme)?\s*(groet(en)?|kind regards|regards|tot (snel|gauw))\b", re.I)


# helpers ---------------------------------------------------------------------------------------------------------

def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if len(p.strip()) >= 12]


def _norm(sent: str) -> str:
    s = re.sub(r"\d[\d.,]*", "#", sent.lower())
    return re.sub(r"[^\w# ]+", "", s).strip()


def _words(sent: str) -> set[str]:
    return {w for w in _norm(sent).split() if len(w) > 2}


def _similar(a: str, b: str) -> bool:
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.6


def _personal(sent: str, fam: Family | None) -> bool:
    """A sentence about this family (their names, an amount, a date) is not a rule for everyone."""
    names = {p.lower() for p in ((fam.contact_name or "") + " " + (fam.surname or "")).split() if len(p) > 2} if fam else set()
    low = sent.lower()
    return any(re.search(rf"\b{re.escape(n)}\b", low) for n in names) or bool(re.search(r"€|\beur\b|\d{1,2}[-/ ]\d{1,2}", low))


def _team_lead(s: Session, team_id: str | None) -> str:
    lead = s.scalars(select(Employee).where(Employee.role == "team_lead", Employee.team_id == team_id)).first() if team_id else None
    lead = lead or s.scalars(select(Employee).where(Employee.role == "content")).first()
    return lead.id if lead else "content"


# 1. house rules from edits --------------------------------------------------------------------------------------

def learn_from_edits(s: Session) -> dict:
    since = utcnow() - timedelta(days=WINDOW_DAYS)
    groups: dict[tuple, list[tuple[str, str, int]]] = defaultdict(list)  # (team, kind, added|removed) -> (sentence, who, draft)
    for d in s.scalars(select(Draft).where(Draft.status == "approved", Draft.kind.in_(LEARN_FROM),
                                           Draft.decided_at >= since)).all():
        if not d.final_body or d.final_body.strip() == (d.body or "").strip():
            continue
        tr = s.get(TripRequest, d.request_id) if d.request_id else None
        fam = s.get(Family, tr.family_id) if tr else None
        team = tr.team_id if tr else (d.data or {}).get("team_id")
        system = " ".join((d.data or {}).get("system_added", []))
        before, after = sentences(d.body), [x for x in sentences(d.final_body) if x not in system]
        for sent in after:
            if not any(_similar(sent, b) for b in before) and not _personal(sent, fam):
                groups[(team, d.kind, "added")].append((sent, d.decided_by or "", d.id))
        for sent in before:
            if not any(_similar(sent, a) for a in after) and not _personal(sent, fam):
                groups[(team, d.kind, "removed")].append((sent, d.decided_by or "", d.id))
    proposed = 0
    for (team, kind, how), rows in groups.items():
        used: set[int] = set()
        for i, (sent, _, _) in enumerate(rows):
            if i in used:
                continue
            cluster = [j for j, (other, _, _) in enumerate(rows) if j not in used and _similar(sent, other)]
            drafts = {rows[j][2] for j in cluster}
            people = {rows[j][1] for j in cluster}
            used.update(cluster)
            if len(drafts) < MIN_DRAFTS or len(people) < MIN_PEOPLE:
                continue
            rid = "rule-" + hashlib.sha256(f"{team}|{kind}|{how}|{_norm(sent)}".encode()).hexdigest()[:10]
            if s.get(KnowledgeItem, rid):
                continue  # proposed before (also when the team lead turned it down: then it stays down)
            label = {"proposal": "voorstellen", "change": "wijzigingen", "followup": "opvolgmails", "extras": "extra's",
                     "answer": "antwoorden", "next_trip": "reisideeën"}[kind]
            body = (f"Specialisten van dit team voegen dit vaak toe aan {label} ({len(drafts)} keer in {WINDOW_DAYS} dagen, "
                    f"door {len(people)} collega's): \"{sent}\" Neem dit voortaan op." if how == "added" else
                    f"Specialisten van dit team halen dit vaak weg uit {label} ({len(drafts)} keer in {WINDOW_DAYS} dagen, "
                    f"door {len(people)} collega's): \"{sent}\" Laat dit voortaan weg.")
            s.add(KnowledgeItem(id=rid, title=f"Huisregel {label}: {sent[:60]}", body=body, destination=None, topic="house_rule",
                                owner_id=_team_lead(s, team), status="proposed", review_by=clock_today() + timedelta(days=180),
                                tags=[f"team:{team}", f"kind:{kind}", how], source=f"learned:edits:{len(drafts)}"))
            proposed += 1
    s.commit()
    return {"house_rules_proposed": proposed}


def house_rules(s: Session, team_id: str | None, kind: str) -> list[str]:
    """Approved house rules for this team and kind of mail, for the prompt."""
    rows = s.scalars(select(KnowledgeItem).where(KnowledgeItem.topic == "house_rule", KnowledgeItem.status == "approved")).all()
    return [r.body for r in rows if f"kind:{kind}" in (r.tags or []) and (f"team:{team_id}" in (r.tags or []) or "team:all" in (r.tags or []))]


# 2. examples from outcomes --------------------------------------------------------------------------------------

def _anonymous(text: str, fam: Family | None) -> str:
    lines = [ln for ln in (text or "").splitlines()]
    while lines and (not lines[0].strip() or GREETING_LINE.match(lines[0])):
        lines.pop(0)
    for i, ln in enumerate(lines):
        if SIGN_OFF_LINE.match(ln):
            lines = lines[:i]
            break
    out = "\n".join(lines).strip()
    if fam:
        for n in sorted({p for p in ((fam.contact_name or "") + " " + (fam.surname or "")).split() if len(p) > 2}, key=len, reverse=True):
            out = re.sub(rf"\b{re.escape(n)}\b", "[naam]", out)
    # Learned text is shown to the model when it writes for OTHER families: run it through the same anonymiser as
    # real data (children's names, phone numbers, addresses, booking numbers). When unsure, it is not learned.
    from .anonymise import Anonymiser, Refused
    try:
        return Anonymiser().scrub(out, [fam.contact_name, fam.surname] if fam else [], True).text
    except Refused:
        return ""


def learn_from_outcomes(s: Session) -> dict:
    """Booked or turned down: the proposal as sent becomes an example, labelled with how it ended."""
    added = updated = 0
    for tr in s.scalars(select(TripRequest).where(TripRequest.status.in_(["booked", "lost"]))).all():
        sent = s.scalars(select(Draft).where(Draft.request_id == tr.id, Draft.kind.in_(["proposal", "change"]),
                                             Draft.status == "approved").order_by(Draft.decided_at.desc())).first()
        if sent is None:
            continue
        pid = f"learned-{sent.id}"
        row = s.get(PastProposal, pid)
        if row is not None:
            if row.booked != (tr.status == "booked"):
                row.booked = tr.status == "booked"
                updated += 1
            continue
        fam = s.get(Family, tr.family_id)
        price = ((sent.data or {}).get("price") or {})
        persons = price.get("persons") or ((fam.adults if fam else 2) + len(fam.child_ages if fam else []))
        route = [{"stop": r["stop"], "nights": r["nights"], "hotel": r["hotel"]} for r in (sent.data or {}).get("route", [])]
        text = _anonymous(sent.final_body or sent.body, fam)
        if not text:
            continue  # the anonymiser was not sure: better no example than one with a family's details
        s.add(PastProposal(id=pid, destination=tr.destination, days=tr.days, route=route,
                           party=f"{fam.adults if fam else 2} volwassenen, kinderen {', '.join(map(str, fam.child_ages)) if fam else ''}",
                           text=text, booked=tr.status == "booked",
                           price_pp_eur=round(float(price.get("sell_eur") or 0) / max(persons, 1), 2),
                           synthetic=bool(fam.synthetic) if fam else True, source_draft_id=sent.id,
                           child_ages=list(fam.child_ages or []) if fam else []))
        added += 1
    s.commit()
    return {"examples_added": added, "examples_updated": updated}


def rank_examples(rows: list[PastProposal], days: int, child_ages: list[int] | None = None, k: int = 3) -> list[PastProposal]:
    """Booked first; then the most alike: trip length, children's ages, and our own recent texts over old ones."""
    ages = sorted(child_ages or [])

    def score(p: PastProposal) -> float:
        sc = 0.0 if p.booked else 10.0
        sc += abs(p.days - days) / 3
        if ages and p.child_ages:
            theirs = sorted(p.child_ages)
            sc += abs(len(theirs) - len(ages)) + abs((sum(theirs) / len(theirs)) - (sum(ages) / len(ages))) / 3
        if p.source_draft_id is None:
            sc += 0.5  # seeded examples weigh a little less than what our own specialists sent
        return sc
    return sorted(rows, key=score)[:k]


# 3. knowledge from answers --------------------------------------------------------------------------------------

def learn_from_answer(s: Session, d: Draft) -> KnowledgeItem | None:
    """A specialist answered a family question the brain could not: propose the answer as a knowledge note."""
    gap_id = (d.data or {}).get("gap_id")
    if d.kind != "answer" or not gap_id:
        return None
    gap = s.get(KnowledgeGap, gap_id)
    if gap is None or gap.status != "open":
        return None
    tr = s.get(TripRequest, d.request_id) if d.request_id else None
    fam = s.get(Family, tr.family_id) if tr else None
    core = _anonymous(d.final_body or d.body, fam)
    if len(core) < 40 or "[schrijf hier" in core.lower():
        return None
    from .knowledge.store import KnowledgeBase
    iid = f"gap-{gap.id}"
    if s.get(KnowledgeItem, iid):
        return None
    item = KnowledgeBase(s).propose(iid, gap.question[:90], core, _team_lead(s, gap.team_id), gap.destination, "faq",
                                    clock_today() + timedelta(days=180))
    item.tags = ["learned:answer"]
    item.source = f"learned:answer:{d.id}"
    gap.status = "written"
    s.commit()
    return item


def nightly(s: Session) -> dict:
    return learn_from_edits(s) | learn_from_outcomes(s)
