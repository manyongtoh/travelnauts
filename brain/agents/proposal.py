"""Proposal writer: route from similar earlier proposals, prices from the calculation service, facts from
approved knowledge, text in the house voice. Everything it reads comes through the tool server.

Before the draft is saved, the output checks run: every euro amount must come from the calculation, no
health advice, no hotels that are not in the offer. If a check fails, the large model tries once more;
if it still fails, the draft is saved with the problems listed and cannot be approved unchanged.
"""
from __future__ import annotations

import random

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Draft, Employee, PriceItem, TripRequest
from ..guardrails import check_output, fix_dashes
from ..identity import agent
from ..synth.generate import route_for
from ..synth.world import DESTINATIONS
from ..toolserver import server
from .common import audit, run_step

ME = agent("proposal_writer")


class ProposalText(BaseModel):
    subject: str
    body: str
    used_sources: list[str]


INSTRUCTIONS = "See the agent layer in prompts/agents/proposal.md."


def pick_activities(s: Session, destination: str, stop: str, child_ages: list[int], wishes: list[str], k: int = 2) -> list[str]:
    youngest = min(child_ages) if child_ages else 18
    items = list(s.scalars(select(PriceItem).where(PriceItem.destination == destination, PriceItem.kind == "excursion",
                                                   PriceItem.stop == stop)).all())
    ok = [i for i in items if i.min_child_age <= youngest]
    wish_words = {w for wish in wishes for w in wish.lower().replace(":", " ").replace(",", " ").split() if len(w) > 4}
    ok.sort(key=lambda i: -sum(w in i.name.lower() for w in wish_words))
    return [i.name for i in ok[:k]]


def build_route(s: Session, tr: dict, child_ages: list[int] | None = None) -> tuple[list[dict], list[dict]]:
    examples = server.call(s, ME, "examples.search", destination=tr["destination"], days=tr["days"], child_ages=child_ages)
    base = next((p for p in examples if p["days"] == tr["days"] and all(r.get("hotel") for r in p["route"])), None)
    route = [dict(r) for r in base["route"]] if base else route_for(random.Random(tr["id"]), tr["destination"], tr["days"])
    return avoid_weak_partners(s, tr["destination"], route), examples


def avoid_weak_partners(s: Session, destination: str, route: list[dict]) -> list[dict]:
    """Swap a hotel that measurably lets families down (complaints, or rarely answers) for another at the same stop."""
    from ..db import Partner
    from ..partner_scores import scores
    weak = lambda p: p is not None and (sc := scores(p))["measured"] and (sc["complaints"] >= 2 or sc["reliability"] < 0.5)  # noqa: E731
    hotels = s.scalars(select(PriceItem).where(PriceItem.destination == destination, PriceItem.kind == "hotel")).all()
    for r in route:
        if weak(s.scalars(select(Partner).where(Partner.name == r["hotel"])).first()):
            alt = next((h for h in hotels if h.stop == r["stop"] and h.name != r["hotel"]
                        and not weak(s.scalars(select(Partner).where(Partner.name == h.name)).first())), None)
            if alt:
                r["swapped_from"], r["hotel"] = r["hotel"], alt.name
    return route


def hotels_for(s: Session, destination: str) -> set[str]:
    return {i.name for i in s.scalars(select(PriceItem).where(PriceItem.destination == destination, PriceItem.kind == "hotel")).all()}


def write_proposal(s: Session, request_id: str) -> Draft:
    tr = server.call(s, ME, "ts.read_trip", request_id=request_id)
    fam = server.call(s, ME, "ts.read_relation", family_id=tr["family_id"])
    spec = s.get(Employee, tr["specialist_id"]) if tr["specialist_id"] else None
    with audit(s, "proposal_writer", request_id, f"{tr['destination']} {tr['days']}d") as box:
        route, examples = build_route(s, tr, fam["child_ages"])
        for r in route:
            r["activities"] = pick_activities(s, tr["destination"], r["stop"], fam["child_ages"], tr["wishes"])
        calc = server.call(s, ME, "calc.quote", destination=tr["destination"], route=route, adults=fam["adults"],
                           child_ages=fam["child_ages"], excursions=[a for r in route for a in r["activities"]],
                           request_id=request_id)
        d = DESTINATIONS[tr["destination"]]
        hits = server.call(s, ME, "knowledge.search", query=f"beste reistijd {d['nl']}", destination=tr["destination"], k=1)
        for r in route:
            hits += server.call(s, ME, "knowledge.search", query=f"{r['stop']} met kinderen", destination=tr["destination"], k=1)
        seen, knowledge = set(), []
        for h in hits:
            if h["id"] not in seen:
                seen.add(h["id"])
                knowledge.append({"id": h["id"], "title": h["title"], "text": h["body"], "outdated": h["outdated"]})
        ctx = {
            "family": {"name": fam["contact_name"], "surname": fam["surname"], "adults": fam["adults"], "child_ages": fam["child_ages"],
                       "history": fam.get("history", {})},
            "house_rules": __import__("brain.learning", fromlist=["x"]).house_rules(s, tr.get("team_id"), "proposal"),
            "trip": {"destination": d["nl"], "days": tr["days"], "month": tr["depart_month"], "budget_eur": tr["budget_eur"],
                     "wishes": tr["wishes"]},
            "route": route,
            "price": {k: v for k, v in calc.items() if k != "lines"},
            "knowledge": knowledge,
            "specialist": spec.name if spec else "het team van Travelnauts",
            "examples": [e["text"] for e in examples[:1]],
        }
        known, in_route = hotels_for(s, tr["destination"]), {r["hotel"] for r in route}
        allowed = [calc["sell_eur"]] + ([tr["budget_eur"]] if tr["budget_eur"] else [])
        out, _ = run_step(s, "proposal", ProposalText, INSTRUCTIONS, ctx)
        problems = check_output(out.body, allowed, known, in_route)
        if problems:
            out, _ = run_step(s, "proposal", ProposalText, INSTRUCTIONS + "\nFix: " + "; ".join(problems), ctx, tier="large", escalated=True)
            problems = check_output(out.body, allowed, known, in_route)
        body = fix_dashes(out.body)
        valid_ids = {k["id"] for k in knowledge}
        used = [i for i in out.used_sources if i in valid_ids]
        sources = [{"type": "knowledge", **{k: v for k, v in next(h for h in hits if h["id"] == i).items() if k != "body"}} for i in used] + \
                  [{"type": "past_proposal", "id": e["id"]} for e in examples] + \
                  [{"type": "quote", "id": calc["quote_id"], "price_version": calc["price_version"]}]
        plan = {"days": [{"stop": r["stop"], "nights": r["nights"], "hotel": r["hotel"], "activities": r["activities"]} for r in route]}
        vtb = server.call(s, ME, "ts.draft_reisplan", request_id=request_id, plan=plan)
        draft = Draft(kind="proposal", request_id=request_id, title=out.subject, body=body,
                      data={"route": route, "price": calc, "vtb": vtb, "problems": problems,
                            "warnings": [f"Controle: {p}" for p in problems],
                            "outdated_sources": [k["id"] for k in knowledge if k["outdated"]]},
                      sources=sources)
        s.add(draft)
        s.get(TripRequest, request_id).status = "proposal_draft"
        s.commit()
        box["sources"] = sources
        box["output"] = f"draft {draft.id}: {out.subject} EUR {calc['sell_eur']}{' with problems' if problems else ''}"
    return draft
