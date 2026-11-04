"""Galileo helper: writes the Galileo commands for flight availability and booking. The agent never
runs them; the specialist checks and runs them in Galileo.

The command formats below are common Galileo (Travelport) patterns used as PLACEHOLDERS. Replace
them with Travelnauts' own command list before the anonymised data stage.
"""
from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import Draft, Family, TripRequest
from ..synth.world import DESTINATIONS
from .common import audit, run_step

MONTHS_NL = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
             "november", "december"]
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# What a command may look like. Anything else is flagged for the specialist.
ALLOWED = [
    re.compile(r"^A\d{2}[A-Z]{3}[A-Z]{3}[A-Z]{3}(\*[A-Z0-9]{2})?$"),  # availability
    re.compile(r"^0\d[A-Z]\d$"),                                     # sell from availability line
    re.compile(r"^N\.[A-Z]+/[A-Z0-9]+(MR|MRS|MS|CHD)(\*C\d{2})?$"),     # name
    re.compile(r"^P\.AMSB\*TRAVELNAUTS$"),                           # agency phone (placeholder)
    re.compile(r"^T\.TAU/\d{2}[A-Z]{3}$"),                           # ticketing time limit
    re.compile(r"^R\.[A-Z]+$"),                                      # received from
    re.compile(r"^\*R$"),                                            # display booking
]


class Command(BaseModel):
    cmd: str
    explain: str


class GalileoCommands(BaseModel):
    commands: list[Command]
    notes: list[str] = []


INSTRUCTIONS = (
    "Write the Galileo commands for CONTEXT.flight: availability out and back, sell, one name per traveller (children "
    "with CHD and age), agency phone, ticketing time limit, received from, display. One command per item with a short "
    "Dutch explanation. Do not end or ticket the booking: the specialist does that."
)


def first_saturday(month_nl: str, today: date | None = None) -> date:
    today = today or date.today()
    m = MONTHS_NL.index(month_nl) + 1 if month_nl in MONTHS_NL else today.month
    y = today.year if m > today.month else today.year + 1
    d = date(y, m, 1)
    while d.weekday() != 5:
        d = d.replace(day=d.day + 1)
    return d


def check(cmds: list[Command]) -> list[str]:
    return [f"Controleer '{c.cmd}': onbekend formaat" for c in cmds if not any(p.match(c.cmd) for p in ALLOWED)]


def write_commands(s: Session, request_id: str) -> Draft:
    tr = s.get(TripRequest, request_id)
    fam = s.get(Family, tr.family_id)
    dest = DESTINATIONS[tr.destination]
    out_date = first_saturday(tr.depart_month)
    from datetime import timedelta
    back_date = out_date + timedelta(days=tr.days - 1)
    fmt = lambda d: f"{d.day:02d}{MON[d.month - 1]}"
    with audit(s, "galileo_helper", request_id) as box:
        travellers = [{"surname": fam.surname.upper().replace(" ", ""), "first": fam.contact_name.split()[0].upper(),
                       "type": "adult"}]
        if fam.adults == 2:
            travellers.append({"surname": fam.surname.upper().replace(" ", ""), "first": "PARTNER", "type": "adult"})
        for i, age in enumerate(fam.child_ages):
            travellers.append({"surname": fam.surname.upper().replace(" ", ""), "first": f"KIND{i + 1}", "type": "child", "age": age})
        ctx = {"flight": {"from": "AMS", "to": dest["airport"], "out": fmt(out_date), "back": fmt(back_date),
                          "travellers": travellers, "seats": len(travellers), "class": "Y",
                          "ticket_by": fmt(date.today() + timedelta(days=3))},
               "note": "Dates are the first Saturday of the travel month, to be confirmed with the family."}
        from ..identity import agent
        from ..toolserver import server
        me = agent("galileo_helper")
        out, _ = run_step(s, "galileo", GalileoCommands, INSTRUCTIONS, ctx)
        res = server.call(s, me, "galileo.write_commands", commands=[c.cmd for c in out.commands])
        if not res["ok"]:  # the check in code failed: the large model tries once
            out, _ = run_step(s, "galileo", GalileoCommands, INSTRUCTIONS, ctx, tier="large", escalated=True)
        warnings = check(out.commands)
        body = "\n".join(f"{c.cmd:<28} {c.explain}" for c in out.commands)
        d = Draft(kind="galileo", request_id=tr.id, title=f"Galileo: AMS {dest['airport']} {fmt(out_date)}",
                  body=body, data={"commands": [c.model_dump() for c in out.commands], "warnings": warnings + out.notes,
                                   "placeholder_formats": True})
        s.add(d)
        s.commit()
        box["output"] = f"{len(out.commands)} commands, {len(warnings)} warnings"
    return d
