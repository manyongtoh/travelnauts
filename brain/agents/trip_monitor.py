"""Trip monitor (hourly): for trips departing within 48 hours, check each flight. On a delay of more than
an hour or a cancellation, alert the specialist with a draft message for the family. The specialist
decides; rebooking is never done by the agent, emergencies go to the 24/7 line."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Draft, Employee
from ..identity import agent
from ..synth.world import DESTINATIONS
from ..toolserver import server
from .common import audit, run_step
from ..clock import utcnow

ME = agent("trip_monitor")


class TripAlert(BaseModel):
    subject: str
    body: str


INSTRUCTIONS = (
    "Write a short, calm message in Dutch to CONTEXT.family about CONTEXT.flight and its CONTEXT.status. Say what we "
    "already know, that the specialist is looking at options, and give the 24/7 number from CONTEXT.emergency_line. "
    "Do not promise a rebooking or a refund."
)


def run(s: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    alerts = 0
    with audit(s, "trip_monitor", "hourly") as box:
        trips = [t for t in server.call(s, ME, "ts.list_trips", status="booked")
                 if t["depart_date"] and date.fromisoformat(t["depart_date"]) <= (now + timedelta(hours=48)).date()
                 and date.fromisoformat(t["depart_date"]) >= now.date()]
        done = {(d.request_id, (d.data or {}).get("flight")) for d in s.scalars(select(Draft).where(Draft.kind == "trip_alert")).all()}
        for t in trips:
            fam = server.call(s, ME, "ts.read_relation", family_id=t["family_id"])
            for f in t["flights"]:
                f = flight_fields(f)
                if not (f["number"] and f["date"]):  # incomplete flight data from TravelSpirit: the booking check reports it
                    continue
                st = server.call(s, ME, "travel.flight_status", number=f["number"], date=f["date"])
                if (t["id"], f["number"]) in done or not (st["status"] == "cancelled" or st["delay_minutes"] > 60):
                    continue
                spec = s.get(Employee, t["specialist_id"]) if t["specialist_id"] else None
                out, _ = run_step(s, "trip_alert", TripAlert, INSTRUCTIONS, {
                    "family": {"name": fam["contact_name"]}, "flight": f, "status": st,
                    "trip": {"destination": DESTINATIONS[t["destination"]]["nl"]},
                    "specialist": spec.name if spec else "Travelnauts", "emergency_line": "+31 20 000 0000 (sandbox)"})
                s.add(Draft(kind="trip_alert", request_id=t["id"], title=out.subject, body=out.body,
                            data={"flight": f["number"], "status": st, "warnings": [f"Vlucht {f['number']}: {st['status']}"
                                  + (f", {st['delay_minutes']} min vertraging" if st["delay_minutes"] else "")]}))
                alerts += 1
        s.commit()
        box["output"] = f"{len(trips)} trips checked, {alerts} alerts"
    return {"trips": len(trips), "alerts": alerts}


def flight_fields(f: dict) -> dict:
    """TravelSpirit flight rows differ per export; take the usual names and never fail on a missing one."""
    g = lambda *ks: next((f[k] for k in ks if f.get(k)), None)  # noqa: E731
    return {"number": g("number", "flight", "flight_number", "FlightNumber"), "date": g("date", "depart_date", "Date"),
            "from": g("from", "origin", "From") or "?", "to": g("to", "destination", "To") or "?"}
