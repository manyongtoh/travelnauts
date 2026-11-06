"""Booking commands helper: writes the commands for flight availability and booking in the client's booking
system (Amadeus or Galileo, set by `gds` in tenant.toml). The agent never runs them; the specialist checks them and
runs them in one sitting, so the system's login (Amadeus asks for the authenticator after 10 idle minutes) is
needed once instead of per booking.

The command formats below are common Amadeus and Galileo (Travelport) patterns used as PLACEHOLDERS. Replace them
with the client's own command list before the anonymised data stage. The agency phone entry comes from the
tenant config. No dialect has a command that ends, tickets or cancels a booking: the specialist does that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..clock import today as clock_today
from ..db import Draft, Family, TripRequest
from ..synth.world import DESTINATIONS
from .common import audit, run_step

MONTHS_NL = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
             "november", "december"]
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


@dataclass(frozen=True)
class Dialect:
    key: str
    label: str
    allowed: tuple[re.Pattern, ...]  # what a command may look like; anything else is flagged for the specialist
    phone_pattern: str               # what the agency phone entry in tenant.toml must look like
    phone_example: str
    instructions: str


AMADEUS = Dialect(
    key="amadeus", label="Amadeus",
    allowed=(
        re.compile(r"^AN\d{2}[A-Z]{3}[A-Z]{3}[A-Z]{3}(/A[A-Z0-9]{2})?$"),                     # availability
        re.compile(r"^SS\d[A-Z]\d+$"),                                                     # sell from availability line
        re.compile(r"^NM1[A-Z]+/[A-Z0-9]+( (MR|MRS|MS))?(\(CHD(/\d{2}[A-Z]{3}\d{2})?\))?$"),  # name, child with birth date
        re.compile(r"^TKTL\d{2}[A-Z]{3}$"),                                                 # ticketing time limit
        re.compile(r"^RF ?[A-Z]+$"),                                                         # received from
        re.compile(r"^RT$"),                                                                 # display booking
    ),
    phone_pattern=r"^AP [A-Z]{3} [0-9 ]{6,20}-A$", phone_example="AP AMS 020 0000000-A",
    instructions=(
        "Write the Amadeus commands for CONTEXT.flight: availability out and back (AN), sell (SS), one name per "
        "traveller (NM1, children with (CHD/date of birth) or (CHD) when the date is unknown), agency phone, ticketing "
        "time limit (TKTL), received from (RF), display (RT). One command per item with a short Dutch explanation. "
        "Never end (ER), ticket or cancel the booking: the specialist does that."),
)

GALILEO = Dialect(
    key="galileo", label="Galileo",
    allowed=(
        re.compile(r"^A\d{2}[A-Z]{3}[A-Z]{3}[A-Z]{3}(\*[A-Z0-9]{2})?$"),  # availability
        re.compile(r"^0\d[A-Z]\d$"),                                     # sell from availability line
        re.compile(r"^N\.[A-Z]+/[A-Z0-9]+(MR|MRS|MS|CHD)(\*C\d{2})?$"),   # name
        re.compile(r"^T\.TAU/\d{2}[A-Z]{3}$"),                           # ticketing time limit
        re.compile(r"^R\.[A-Z]+$"),                                      # received from
        re.compile(r"^\*R$"),                                            # display booking
    ),
    phone_pattern=r"^P\.[A-Z]{4}\*[A-Z0-9]+$", phone_example="P.AMSB*NAME",
    instructions=(
        "Write the Galileo commands for CONTEXT.flight: availability out and back, sell, one name per traveller "
        "(children with CHD and age), agency phone, ticketing time limit, received from, display. One command per "
        "item with a short Dutch explanation. Do not end or ticket the booking: the specialist does that."),
)

DIALECTS = {d.key: d for d in (AMADEUS, GALILEO)}


def dialect() -> Dialect:
    from ..tenant import tenant
    return DIALECTS[tenant().gds]


def allowed() -> list[re.Pattern]:
    """The client's booking system's patterns plus this client's agency phone entry."""
    from ..tenant import tenant
    return [*dialect().allowed, re.compile("^" + re.escape(tenant().gds_agency_phone) + "$")]


class Command(BaseModel):
    cmd: str
    explain: str


class BookingCommands(BaseModel):
    commands: list[Command]
    notes: list[str] = []




def first_saturday(month_nl: str, today: date | None = None) -> date:
    today = today or clock_today()
    m = MONTHS_NL.index(month_nl) + 1 if month_nl in MONTHS_NL else today.month
    y = today.year if m > today.month else today.year + 1
    d = date(y, m, 1)
    while d.weekday() != 5:
        d = d.replace(day=d.day + 1)
    return d


def check(cmds: list[Command]) -> list[str]:
    return [f"Controleer '{c.cmd}': onbekend formaat" for c in cmds if not any(p.match(c.cmd) for p in allowed())]


def write_commands(s: Session, request_id: str) -> Draft:
    tr = s.get(TripRequest, request_id)
    fam = s.get(Family, tr.family_id)
    dest = DESTINATIONS[tr.destination]
    out_date = first_saturday(tr.depart_month)
    from datetime import timedelta
    back_date = out_date + timedelta(days=tr.days - 1)
    fmt = lambda d: f"{d.day:02d}{MON[d.month - 1]}"
    dia = dialect()
    with audit(s, "gds_helper", request_id) as box:
        travellers = [{"surname": fam.surname.upper().replace(" ", ""), "first": (fam.contact_name.split() or ["ONBEKEND"])[0].upper(),
                       "type": "adult"}]
        if fam.adults == 2:
            travellers.append({"surname": fam.surname.upper().replace(" ", ""), "first": "PARTNER", "type": "adult"})
        for i, age in enumerate(fam.child_ages):
            travellers.append({"surname": fam.surname.upper().replace(" ", ""), "first": f"KIND{i + 1}", "type": "child", "age": age})
        ctx = {"flight": {"from": "AMS", "to": dest["airport"], "out": fmt(out_date), "back": fmt(back_date),
                          "travellers": travellers, "seats": len(travellers), "class": "Y",
                          "ticket_by": fmt(clock_today() + timedelta(days=3))},
               "system": dia.key,
               "note": "Dates are the first Saturday of the travel month, to be confirmed with the family."}
        from ..identity import agent
        from ..toolserver import server
        me = agent("gds_helper")
        out, _ = run_step(s, "gds", BookingCommands, dia.instructions, ctx)
        res = server.call(s, me, "gds.write_commands", commands=[c.cmd for c in out.commands])
        if not res["ok"]:  # the check in code failed: the large model tries once
            out, _ = run_step(s, "gds", BookingCommands, dia.instructions, ctx, tier="large", escalated=True)
        warnings = check(out.commands)
        body = "\n".join(f"{c.cmd:<28} {c.explain}" for c in out.commands)
        d = Draft(kind="gds", request_id=tr.id, title=f"{dia.label}: AMS {dest['airport']} {fmt(out_date)}",
                  body=body, data={"commands": [c.model_dump() for c in out.commands], "warnings": warnings + out.notes,
                                   "placeholder_formats": True, "system": dia.key})
        s.add(d)
        s.commit()
        box["output"] = f"{len(out.commands)} commands, {len(warnings)} warnings"
    return d
