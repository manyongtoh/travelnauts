"""Sales agents from the agents slide, on top of the proposal writer:

  alternatives   two other versions of a proposal: quieter (fewer stops) and cheaper (simpler hotels,
                 fewer paid activities), each priced by the calculation service
  complaint      reads a complaint, links it to the trip, sorts severity, drafts a careful reply and an
                 internal action list; urgent cases go to the team lead. It never promises money back.
  next_trip      suggests a next trip for a family that travelled with us, based on where they have been
                 and how old the children are now
  extras         suggests add-ons that fit the family and are not yet in the offer, with prices
  call_notes     turns a specialist's rough call notes into wishes, changes, open questions and next steps

Everything is a draft for the specialist.
"""
from __future__ import annotations

import random
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Draft, Employee, Mail, PriceItem, TripRequest
from ..tenant import tenant
from ..guardrails import check_output
from ..identity import agent
from ..synth.world import DESTINATIONS
from ..toolserver import server
from .change import latest_version
from .common import audit, run_step
from ..clock import today as clock_today


class MailText(BaseModel):
    subject: str
    body: str


def _spec(s: Session, tr: dict) -> str:
    e = s.get(Employee, tr["specialist_id"]) if tr.get("specialist_id") else None
    return e.name if e else tenant().short_name


# Alternatives --------------------------------------------------------------------------------

def _cheapest_hotel(prices: list[dict], stop: str) -> str | None:
    hotels = sorted((p for p in prices if p["kind"] == "hotel" and p["stop"] == stop), key=lambda p: p["cost_eur"])
    return hotels[0]["name"] if hotels else None


def alternatives(s: Session, request_id: str) -> Draft:
    me = agent("alternatives")
    tr = server.call(s, me, "ts.read_trip", request_id=request_id)
    fam = server.call(s, me, "ts.read_relation", family_id=tr["family_id"])
    base = latest_version(s, request_id)
    if base is None:
        raise ValueError("Write a proposal first")
    with audit(s, "alternatives", request_id) as box:
        route = base.data["route"]
        prices = server.call(s, me, "prices.read", destination=tr["destination"])
        # Quieter: keep first and last stop and the longest middle stop; spread the nights.
        nights = sum(r["nights"] for r in route)
        middle = sorted(route[1:-1], key=lambda r: -r["nights"])[:1]
        quiet = [dict(r) for r in [route[0], *middle, route[-1]]] if len(route) > 2 else [dict(r) for r in route]
        extra = nights - sum(r["nights"] for r in quiet)
        for i in range(extra):
            quiet[(len(quiet) - 1 - i) % len(quiet)]["nights"] += 1
        # Cheaper: cheapest hotel per stop, one paid activity per stop at most.
        cheap = [dict(r, hotel=_cheapest_hotel(prices, r["stop"]) or r["hotel"], activities=r.get("activities", [])[:1]) for r in route]
        versions = []
        for key, label, rt in (("quiet", "Rustiger", quiet), ("cheaper", "Voordeliger", cheap)):
            q = server.call(s, me, "calc.quote", destination=tr["destination"], route=rt, adults=fam["adults"],
                            child_ages=fam["child_ages"], excursions=[a for r in rt for a in r.get("activities", [])], request_id=request_id)
            versions.append({"key": key, "label": label, "route": rt, "price": q})
        ctx = {"family": {"name": fam["contact_name"]}, "trip": {"destination": DESTINATIONS[tr["destination"]]["nl"],
               "budget_eur": tr["budget_eur"]}, "current": {"route": route, "sell_eur": base.data["price"]["sell_eur"]},
               "versions": [{"label": v["label"], "route": [{"stop": r["stop"], "nights": r["nights"], "hotel": r["hotel"]} for r in v["route"]],
                             "sell_eur": v["price"]["sell_eur"]} for v in versions], "specialist": _spec(s, tr)}
        out, _ = run_step(s, "alternatives", MailText, "Write a short mail in Dutch that offers CONTEXT.versions next to the current "
                          "proposal, with their prices from CONTEXT.versions[].sell_eur. Do not invent prices.", ctx)
        problems = check_output(out.body, [base.data["price"]["sell_eur"]] + [v["price"]["sell_eur"] for v in versions] + ([tr["budget_eur"]] if tr["budget_eur"] else []))
        d = Draft(kind="alternatives", request_id=request_id, title=out.subject, body=out.body,
                  data={"versions": versions, "current_sell_eur": base.data["price"]["sell_eur"], "warnings": problems})
        s.add(d)
        s.commit()
        box["output"] = " / ".join(f"{v['label']} EUR {v['price']['sell_eur']}" for v in versions)
    return d


# Complaints ----------------------------------------------------------------------------------

class ComplaintAssessment(BaseModel):
    severity: str = Field(description="low, medium or high")
    while_travelling: bool
    topics: list[str] = Field(description="for example hotel, transfer, guide, flight, price, communication")
    actions: list[str] = Field(description="internal next steps for our team, in Dutch")
    subject: str
    body: str = Field(description="reply to the family in Dutch")


COMPLAINT_INSTRUCTIONS = (
    "Read the complaint in CONTEXT.mail about the trip in CONTEXT.trip. Judge severity (high when the family is "
    "travelling now and stuck, or safety is involved), list the topics and internal actions, and write a calm, "
    "sincere reply: acknowledge, say what we do now and when they hear from us. Never promise money back, a refund, "
    "compensation or a discount: the team lead decides that. Give the 24/7 number from CONTEXT.emergency_line when "
    "they are travelling."
)
MONEY = ("terugbetal", "refund", "compensatie", "vergoed", "korting", "geld terug", "compensation", "discount")


def complaint(s: Session, mail_id: str) -> Draft:
    me = agent("complaints")
    m = s.get(Mail, mail_id)
    done = [d for d in s.scalars(select(Draft).where(Draft.kind == "complaint_reply")).all() if (d.data or {}).get("mail_id") == mail_id]
    if done:  # safe to repeat
        return done[0]
    with audit(s, "complaints", mail_id, m.subject) as box:
        mail = server.call(s, me, "ts.read_mail", mail_id=mail_id)
        trips = server.call(s, me, "ts.list_trips", family_id=m.family_id) if m.family_id else []
        linked = (m.triage or {}).get("request_id")  # triage found the trip they are on right now
        trip = next((t for t in trips if t["id"] == linked), None) or complained_trip(trips)
        fam = server.call(s, me, "ts.read_relation", family_id=m.family_id) if m.family_id else {"contact_name": ""}
        ctx = {"mail": {"subject": mail["subject"], "body": mail["body"]},
               "family": {"name": fam["contact_name"], "first_name": (fam["contact_name"] or "").split(" ")[0]},
               "trip": {"destination": DESTINATIONS[trip["destination"]]["nl"], "depart_date": trip["depart_date"],
                        "status": trip["status"]} if trip else None,
               "emergency_line": tenant().emergency_line, "specialist": _spec(s, trip) if trip else tenant().short_name}
        out, _ = run_step(s, "complaint_reply", ComplaintAssessment, COMPLAINT_INSTRUCTIONS, ctx)
        if (m.triage or {}).get("while_travelling"):  # the dates decide this, not the model: on the road is always high
            out.while_travelling, out.severity = True, "high"
        promises = [w for w in MONEY if w in out.body.lower()]
        warnings = (["Antwoord belooft geld of korting: de teamleider beslist daarover"] if promises else [])
        if out.severity == "high":
            warnings.append("Hoge prioriteit: teamleider is op de hoogte gebracht")
        d = Draft(kind="complaint_reply", request_id=trip["id"] if trip else None, title=out.subject, body=out.body,
                  data={"mail_id": mail_id, "severity": out.severity, "while_travelling": out.while_travelling, "topics": out.topics,
                        "actions": out.actions, "warnings": warnings,
                        "team_id": (s.get(TripRequest, trip["id"]).team_id if trip else None) or (m.triage or {}).get("team_id")})
        s.add(d)
        m.status = "done"
        s.commit()
        box["output"] = f"{out.severity} {','.join(out.topics)}"
    return d


# Next trip -----------------------------------------------------------------------------------

def _min_age(prices: list[dict], destination: str) -> int:
    ages = [p["min_child_age"] for p in prices if p["destination"] == destination and p["kind"] == "excursion"]
    return max(ages) if ages else 0


def next_trip(s: Session, family_id: str) -> Draft:
    me = agent("next_trip")
    with audit(s, "next_trip", family_id) as box:
        fam = server.call(s, me, "ts.read_relation", family_id=family_id)
        trips = server.call(s, me, "ts.list_trips", family_id=family_id)
        been = set(fam.get("past_destinations") or []) | {t["destination"] for t in trips}
        prices = server.call(s, me, "prices.read")
        youngest = min(fam["child_ages"]) if fam["child_ages"] else 18
        options = []
        for key, d in DESTINATIONS.items():
            if key in been:
                continue
            fits = sum(1 for p in prices if p["destination"] == key and p["kind"] == "excursion" and p["min_child_age"] <= youngest)
            total = sum(1 for p in prices if p["destination"] == key and p["kind"] == "excursion")
            options.append({"destination": key, "name": d["nl"], "best": d["best"], "share_fits": round(fits / max(total, 1), 2),
                            "flight_pp": d["flight_pp"]})
        rng = random.Random(family_id)
        options.sort(key=lambda o: (-o["share_fits"], o["flight_pp"], rng.random()))
        pick = options[:2]
        season = [server.call(s, me, "knowledge.search", query=f"beste reistijd {o['name']}", destination=o["destination"], k=1) for o in pick]
        ctx = {"family": {"name": fam["contact_name"], "child_ages": fam["child_ages"]},
               "been_to": [DESTINATIONS[b]["nl"] for b in been if b in DESTINATIONS], "suggestions": pick,
               "knowledge": [h[0]["body"] for h in season if h]}
        out, _ = run_step(s, "next_trip", MailText, "Write a short, personal mail in Dutch suggesting CONTEXT.suggestions as a "
                          "next family trip, with one reason each that fits the children's ages, and the best season from "
                          "CONTEXT.knowledge. No prices. No pressure.", ctx)
        from ..db import Employee
        from .triage import best_specialist, team_for
        team = team_for(s, pick[0]["destination"]) if pick else None
        # the family's own specialist if they are still here and in the right team; else the one who knows it best
        known = [s.get(Employee, t["specialist_id"]) for t in reversed(trips) if t.get("specialist_id")]
        spec = next((e for e in known if e and e.active and team and e.team_id == team.id), None) \
            or (best_specialist(s, team.id, pick[0]["destination"]) if team else None)
        d = Draft(kind="next_trip", request_id=trips[0]["id"] if trips else None, title=out.subject, body=out.body,
                  data={"family_id": family_id, "suggestions": pick, "team_id": team.id if team else None,
                        "specialist_id": spec.id if spec else None})
        s.add(d)
        s.commit()
        box["output"] = ", ".join(o["name"] for o in pick)
    return d


# Extras --------------------------------------------------------------------------------------

def extras(s: Session, request_id: str) -> Draft:
    me = agent("extras")
    tr = server.call(s, me, "ts.read_trip", request_id=request_id)
    fam = server.call(s, me, "ts.read_relation", family_id=tr["family_id"])
    base = latest_version(s, request_id)
    if base is None:
        raise ValueError("Write a proposal first")
    with audit(s, "extras", request_id) as box:
        route = base.data["route"]
        stops = {r["stop"] for r in route}
        have = {a for r in route for a in r.get("activities", [])}
        youngest = min(fam["child_ages"]) if fam["child_ages"] else 18
        persons = fam["adults"] + len(fam["child_ages"])
        wishes = " ".join(tr["wishes"]).lower()
        cands = [p for p in server.call(s, me, "prices.read", destination=tr["destination"])
                 if p["kind"] == "excursion" and p["stop"] in stops and p["name"] not in have and p["min_child_age"] <= youngest]
        cands.sort(key=lambda p: (-sum(w in p["name"].lower() for w in wishes.split() if len(w) > 4), p["cost_eur"]))
        picks = []
        for p in cands[:4]:
            from ..pricing import margin
            sell = round(p["cost_eur"] * persons * (1 + margin("excursion")))  # same rule as the calculation service
            picks.append({"name": p["name"], "stop": p["stop"], "price_eur": sell, "price_item": p["id"]})
        policy = server.call(s, me, "knowledge.search", query="reisverzekering annuleringsverzekering", k=1)
        ctx = {"family": {"name": fam["contact_name"], "child_ages": fam["child_ages"]}, "extras": picks,
               "insurance_policy": policy[0]["body"] if policy else None, "specialist": _spec(s, tr)}
        out, _ = run_step(s, "extras", MailText, "Write a short note in Dutch to CONTEXT.family offering CONTEXT.extras, each with "
                          "its price for the whole family, and mention the insurance advice in CONTEXT.insurance_policy.", ctx)
        problems = check_output(out.body, [p["price_eur"] for p in picks])
        d = Draft(kind="extras", request_id=request_id, title=out.subject, body=out.body, data={"extras": picks, "warnings": problems})
        s.add(d)
        s.commit()
        box["output"] = f"{len(picks)} extras"
    return d


# Call notes ----------------------------------------------------------------------------------

class CallNotes(BaseModel):
    summary: str
    wishes: list[str] = []
    changes: list[str] = []
    open_questions: list[str] = []
    next_steps: list[str] = []
    budget_eur: float | None = None
    days: int | None = None


CALL_INSTRUCTIONS = ("Turn CONTEXT.notes, a specialist's rough notes of a phone call with the family about CONTEXT.trip, "
                     "into a short summary in Dutch, the wishes, requested changes, open questions and next steps. Only "
                     "what the notes say.")


def call_notes(s: Session, request_id: str, notes: str) -> Draft:
    me = agent("call_notes")
    tr = server.call(s, me, "ts.read_trip", request_id=request_id)
    with audit(s, "call_notes", request_id) as box:
        out, _ = run_step(s, "call_notes", CallNotes, CALL_INSTRUCTIONS,
                          {"notes": notes, "trip": {"destination": DESTINATIONS[tr["destination"]]["nl"], "days": tr["days"],
                                                    "wishes": tr["wishes"]}})
        row = s.get(TripRequest, request_id)
        row.wishes = sorted(set(row.wishes or []) | set(out.wishes))
        if out.budget_eur:
            row.budget_eur = out.budget_eur
        if out.days:
            row.days = out.days
        body = "\n".join([out.summary, "", "Wensen: " + (", ".join(out.wishes) or "geen nieuwe"),
                          "Wijzigingen: " + (", ".join(out.changes) or "geen"),
                          "Open vragen: " + (", ".join(out.open_questions) or "geen"),
                          "Volgende stappen: " + (", ".join(out.next_steps) or "geen")])
        d = Draft(kind="call_notes", request_id=request_id, title=f"Gespreksnotitie {clock_today().isoformat()}", body=body,
                  data=out.model_dump(), status="approved", final_body=body, edit_share=0.0)
        s.add(d)
        s.commit()
        box["output"] = out.summary[:120]
    return d


def complained_trip(trips: list[dict]) -> dict | None:
    """A complaint is about a booked trip: the one that started most recently, else the next one coming up."""
    from ..clock import today
    booked = [t for t in trips if t["status"] == "booked"]
    started = sorted((t for t in booked if t.get("depart_date") and t["depart_date"] <= today().isoformat()),
                     key=lambda t: t["depart_date"], reverse=True)
    coming = sorted((t for t in booked if t not in started), key=lambda t: t.get("depart_date") or "9999")
    return (started or coming or [None])[0]
