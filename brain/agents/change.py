"""Change agent: a family asks to change their proposal. The agent works out what they want, applies
what can be applied to the route, recalculates the price, and drafts a reply with the new version.
Changes it cannot apply itself (dates, transport, anything unclear) go to the specialist as a list.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Draft, Employee, Family, Mail, TripRequest
from ..identity import agent
from ..toolserver import server
from ..synth.world import DESTINATIONS
from .common import audit, run_step

ME = agent("change")
AUTO_OPS = ("extend_stop", "shorten_stop", "remove_stop")


class ChangeOp(BaseModel):
    op: Literal["extend_stop", "shorten_stop", "remove_stop", "shift_dates", "swap_transport", "other"]
    stop: str | None = Field(None, description="exactly as in CONTEXT.route[].stop, or null")
    nights: int = Field(0, description="number of nights to add or remove")
    note: str = ""


class ChangePlan(BaseModel):
    ops: list[ChangeOp]


class ChangeReply(BaseModel):
    subject: str
    body: str


PLAN_INSTRUCTIONS = (
    "Read CONTEXT.mail and list the changes the family asks for to the trip in CONTEXT.route. Use extend_stop or "
    "shorten_stop with the number of nights, remove_stop to skip a stop, shift_dates for other departure dates, "
    "swap_transport for another way of travelling, other for anything else. 'Aan het strand' means the last stop."
)
REPLY_INSTRUCTIONS = (
    "Write a short reply in Dutch to CONTEXT.family confirming the changes in CONTEXT.applied, the new route in "
    "CONTEXT.route_after and the new indicative price CONTEXT.price_after (compared with CONTEXT.price_before). "
    "For CONTEXT.manual say the specialist will come back on it. Say we still check availability with partners."
)


def latest_version(s: Session, request_id: str) -> Draft | None:
    return s.scalars(select(Draft).where(Draft.request_id == request_id, Draft.kind.in_(["proposal", "change"]),
                                         Draft.status != "rejected").order_by(Draft.id.desc())).first()


def apply_ops(route: list[dict], ops: list[ChangeOp]) -> tuple[list[dict], list[ChangeOp], list[ChangeOp]]:
    new = [dict(r) for r in route]
    applied, manual = [], []
    for o in ops:
        idx = next((i for i, r in enumerate(new) if o.stop and r["stop"].lower() == o.stop.lower()), None)
        if o.op not in AUTO_OPS or idx is None:
            manual.append(o)
            continue
        if o.op == "extend_stop" and o.nights > 0:
            new[idx]["nights"] += o.nights
        elif o.op == "shorten_stop" and 0 < o.nights < new[idx]["nights"]:
            new[idx]["nights"] -= o.nights
        elif o.op == "remove_stop" and len(new) > 2 and idx not in (0, len(new) - 1):
            new.pop(idx)
        else:
            manual.append(o)
            continue
        applied.append(o)
    return new, applied, manual


def handle_change(s: Session, mail_id: str) -> Draft:
    m = s.get(Mail, mail_id)
    rid = (m.triage or {}).get("request_id")
    if not rid:
        raise ValueError("This mail is not linked to a trip")
    tr = s.get(TripRequest, rid)
    fam = s.get(Family, tr.family_id)
    base = latest_version(s, rid)
    if base is None:
        raise ValueError("No proposal to change yet")
    spec = s.get(Employee, tr.specialist_id) if tr.specialist_id else None
    with audit(s, "change", rid, m.subject) as box:
        route = base.data["route"]
        plan, _ = run_step(s, "change_plan", ChangePlan, PLAN_INSTRUCTIONS,
                           {"mail": {"subject": m.subject, "body": m.body}, "route": route})
        new_route, applied, manual = apply_ops(route, plan.ops)
        before = base.data["price"]
        acts = [a for r in new_route for a in r.get("activities", [])]
        after = server.call(s, ME, "calc.quote", destination=tr.destination, route=new_route, adults=fam.adults,
                            child_ages=fam.child_ages, excursions=acts, request_id=rid)
        days_after = sum(r["nights"] for r in new_route) + 2
        reply, _ = run_step(s, "change_reply", ChangeReply, REPLY_INSTRUCTIONS, {
            "family": {"name": fam.contact_name}, "trip": {"destination": DESTINATIONS[tr.destination]["nl"]},
            "applied": [o.model_dump() for o in applied], "manual": [o.model_dump() for o in manual],
            "route_after": new_route, "days_after": days_after,
            "price_before": before["sell_eur"], "price_after": after["sell_eur"],
            "specialist": spec.name if spec else "Travelnauts"})
        changed = {r["hotel"] for r in new_route} | {r["hotel"] for r in route}
        recheck = sorted(h for h in changed if next((x["nights"] for x in new_route if x["hotel"] == h), None) !=
                         next((x["nights"] for x in route if x["hotel"] == h), None))
        d = Draft(kind="change", request_id=rid, title=reply.subject, body=reply.body, sources=base.sources,
                  data={"mail_id": mail_id, "based_on": base.id, "route_before": route, "route": new_route,
                        "price_before": before, "price": after, "days_before": tr.days, "days_after": days_after,
                        "ops": [o.model_dump() for o in plan.ops], "applied": [o.model_dump() for o in applied],
                        "manual": [o.model_dump() for o in manual],
                        "warnings": ([f"Opnieuw beschikbaarheid vragen: {', '.join(recheck)}"] if recheck else []) +
                                    [f"Voor de specialist: {o.op.replace('_', ' ')}{' ' + o.note if o.note else ''}" for o in manual]})
        s.add(d)
        m.status = "done"
        s.commit()
        box["output"] = f"{len(applied)} applied, {len(manual)} for the specialist, EUR {before['sell_eur']} -> {after['sell_eur']}"
    return d
