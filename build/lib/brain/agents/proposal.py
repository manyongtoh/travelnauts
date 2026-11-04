"""Proposal writer: route from similar earlier proposals, prices from the price list, facts from
approved knowledge, text in the house voice. Result is a draft for the specialist, and a draft
reisplan for the Visual Tour Builder."""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Draft, Employee, Family, PastProposal, PriceItem, TripRequest
from ..knowledge.store import KnowledgeBase
from ..pricing import calculate
from ..synth.generate import route_for
from ..synth.world import DESTINATIONS
import random
from .common import audit, run_step


class ProposalText(BaseModel):
    subject: str
    body: str
    used_sources: list[str]


INSTRUCTIONS = (
    "Write a first proposal mail for CONTEXT.family about the route in CONTEXT.route. Mention each stop with its nights, "
    "hotel and one or two activities from CONTEXT.route[].activities. Use the season from CONTEXT.knowledge. Give the "
    "total price from CONTEXT.price.sell_eur and say it is an indication. Mention CONTEXT.price.warnings only as "
    "'we checken nog'. Do not add facts that are not in CONTEXT. Return the ids of the knowledge items you used."
)


def similar_proposals(s: Session, destination: str, days: int, k: int = 3) -> list[PastProposal]:
    rows = list(s.scalars(select(PastProposal).where(PastProposal.destination == destination)).all())
    rows.sort(key=lambda p: (not p.booked, abs(p.days - days)))
    return rows[:k]


def pick_activities(s: Session, destination: str, stop: str, child_ages: list[int], wishes: list[str], k: int = 2) -> list[str]:
    youngest = min(child_ages) if child_ages else 18
    items = list(s.scalars(select(PriceItem).where(PriceItem.destination == destination, PriceItem.kind == "excursion",
                                                   PriceItem.stop == stop)).all())
    ok = [i for i in items if i.min_child_age <= youngest]
    wish_words = {w for wish in wishes for w in wish.lower().replace(":", " ").replace(",", " ").split() if len(w) > 4}
    ok.sort(key=lambda i: -sum(w in i.name.lower() for w in wish_words))
    return [i.name for i in ok[:k]]


def build_route(s: Session, tr: TripRequest) -> tuple[list[dict], list[str]]:
    examples = similar_proposals(s, tr.destination, tr.days)
    base = next((p for p in examples if p.days == tr.days), None)
    if base:
        route = [dict(r) for r in base.route]
    else:
        route = route_for(random.Random(tr.id), tr.destination, tr.days)
    return route, [p.id for p in examples]


def write_proposal(s: Session, request_id: str) -> Draft:
    tr = s.get(TripRequest, request_id)
    if tr is None:
        raise KeyError(request_id)
    fam = s.get(Family, tr.family_id)
    spec = s.get(Employee, tr.specialist_id) if tr.specialist_id else None
    with audit(s, "proposal_writer", request_id, f"{tr.destination} {tr.days}d") as box:
        route, example_ids = build_route(s, tr)
        for r in route:
            r["activities"] = pick_activities(s, tr.destination, r["stop"], fam.child_ages, tr.wishes)
        calc = calculate(s, tr.destination, route, fam.adults, fam.child_ages,
                         [a for r in route for a in r["activities"]])
        kb = KnowledgeBase(s)
        d = DESTINATIONS[tr.destination]
        hits = kb.search(f"beste reistijd {d['nl']}", tr.destination, k=1) + \
            [h for r in route for h in kb.search(f"{r['stop']} met kinderen", tr.destination, k=1)]
        seen, knowledge = set(), []
        for h in hits:
            if h.id not in seen:
                seen.add(h.id)
                knowledge.append({"id": h.id, "title": h.title, "text": h.body, "outdated": h.outdated})
        ctx = {
            "family": {"name": fam.contact_name, "surname": fam.surname, "adults": fam.adults, "child_ages": fam.child_ages},
            "trip": {"destination": d["nl"], "days": tr.days, "month": tr.depart_month, "budget_eur": tr.budget_eur,
                     "wishes": tr.wishes},
            "route": route,
            "price": calc.as_dict() | {"lines": None},
            "knowledge": knowledge,
            "specialist": spec.name if spec else "het team van Travelnauts",
            "examples": [s.get(PastProposal, i).text for i in example_ids[:1]],
        }
        out, _ = run_step("proposal", ProposalText, INSTRUCTIONS, ctx)
        valid_ids = {k["id"] for k in knowledge}
        used = [i for i in out.used_sources if i in valid_ids]
        sources = [{"type": "knowledge", **next(h.cite() for h in hits if h.id == i)} for i in used] + \
                  [{"type": "past_proposal", "id": i} for i in example_ids] + \
                  [{"type": "price_list", "id": l["price_item"]} for l in calc.as_dict()["lines"]]
        plan = {"days": [{"stop": r["stop"], "nights": r["nights"], "hotel": r["hotel"], "activities": r["activities"]}
                         for r in route]}
        from ..travelspirit.client import get_travelspirit
        vtb = get_travelspirit(s).draft_reisplan(tr.id, plan)
        draft = Draft(kind="proposal", request_id=tr.id, title=out.subject, body=out.body,
                      data={"route": route, "price": calc.as_dict(), "vtb": vtb,
                            "outdated_sources": [k["id"] for k in knowledge if k["outdated"]]},
                      sources=sources)
        s.add(draft)
        tr.status = "proposal_draft"
        s.commit()
        box["sources"] = sources
        box["output"] = f"draft {draft.id}: {out.subject} EUR {calc.sell}"
    return draft
