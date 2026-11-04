"""What the brain remembers about a family, and children's ages that count up.

Ages: a family writes "kids of 6 and 9" once. Two years later the next-trip idea must think of 8 and 11. So the
brain keeps birth years (from TravelSpirit when it has birth dates, else worked out from the age and the date it
was given) and refreshes child_ages from them every night. The year is approximate (a birthday may not have
passed yet); that is good enough to choose activities, never used for prices (prices use the booking's ages).

History: earlier trips (where, when, booked or not), whether something went wrong, and what they asked for. Agents
get it with the relation, so a proposal can say "after Costa Rica, ..." and never repeats what went wrong.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import today as clock_today
from .db import Draft, Family, TripRequest


def birth_years(ages: list[int], on: date | None = None) -> list[int]:
    year = (on or clock_today()).year
    return [year - int(a) for a in ages]


def ages_now(years: list[int], on: date | None = None) -> list[int]:
    year = (on or clock_today()).year
    return [max(0, year - int(y)) for y in years]


def set_ages(f: Family, ages: list[int], on: date | None = None) -> None:
    """Record ages the family just told us (a new enquiry): they replace what we knew."""
    f.child_ages = [int(a) for a in ages]
    f.child_birth_years = birth_years(ages, on)


def refresh_ages(s: Session) -> int:
    """Nightly: today's ages from the birth years. Families without birth years get them from today's ages."""
    changed = 0
    for f in s.scalars(select(Family)).all():
        if not f.child_birth_years and f.child_ages:
            f.child_birth_years = birth_years(f.child_ages)
            continue
        now = ages_now(f.child_birth_years)
        if f.child_birth_years and now != list(f.child_ages or []):
            f.child_ages = now
            changed += 1
    s.commit()
    return changed


def history(s: Session, family_id: str) -> dict:
    """The family's story with us, without mail text: for agents and the specialist."""
    trips = s.scalars(select(TripRequest).where(TripRequest.family_id == family_id).order_by(TripRequest.created_at)).all()
    ids = {t.id for t in trips}
    complaints = [d for d in s.scalars(select(Draft).where(Draft.kind == "complaint_reply")).all()
                  if d.request_id in ids or (d.data or {}).get("family_id") == family_id]
    wishes = Counter(w.lower() for t in trips for w in (t.wishes or []))
    return {
        "trips": [{"destination": t.destination, "year": (t.depart_date or t.created_at.date()).year, "days": t.days,
                   "status": t.status} for t in trips],
        "booked_before": sorted({t.destination for t in trips if t.status == "booked"}),
        "something_went_wrong_before": bool(complaints),  # never repeat it to them; just take extra care
        "often_asks_for": [w for w, _ in wishes.most_common(5)],
    }
