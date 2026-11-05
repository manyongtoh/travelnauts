"""The calculation that today happens in Excel: cost lines, margin per kind, selling price.

Margins come from the tenant's pricing template (tenant.toml in the tenant pack), never from code.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import PriceItem
from .clock import today as clock_today



def margin(kind: str) -> float:
    from .tenant import tenant
    return tenant().pricing.margin(kind)


@dataclass
class Line:
    kind: str
    name: str
    qty: float
    unit_cost: float
    price_item_id: str
    valid: bool = True

    @property
    def cost(self) -> float:
        return round(self.qty * self.unit_cost, 2)

    @property
    def sell(self) -> float:
        return round(self.cost * (1 + margin(self.kind)), 2)


@dataclass
class Calculation:
    lines: list[Line] = field(default_factory=list)
    persons: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def cost(self) -> float:
        return round(sum(l.cost for l in self.lines), 2)

    @property
    def sell(self) -> float:
        return round(sum(l.sell for l in self.lines), -1)

    @property
    def margin(self) -> float:
        return round(self.sell - self.cost, 2)

    def as_dict(self) -> dict:
        return {"persons": self.persons, "cost_eur": self.cost, "sell_eur": self.sell, "margin_eur": self.margin,
                "sell_pp_eur": round(self.sell / max(self.persons, 1), -1), "warnings": self.warnings,
                "lines": [{"kind": l.kind, "name": l.name, "qty": l.qty, "unit_cost": l.unit_cost, "cost": l.cost,
                           "sell": l.sell, "valid": l.valid, "price_item": l.price_item_id} for l in self.lines]}


def calculate(s: Session, destination: str, route: list[dict], adults: int, child_ages: list[int],
              excursions: list[str] | None = None) -> Calculation:
    persons = adults + len(child_ages)
    rooms = math.ceil(persons / 4)
    items = list(s.scalars(select(PriceItem).where(PriceItem.destination == destination)).all())
    calc = Calculation(persons=persons)
    today = clock_today()

    flight = next((i for i in items if i.kind == "flight"), None)
    if flight:
        calc.lines.append(Line("flight", flight.name, persons, flight.cost_eur, flight.id))
    for stop in route:
        hotel = next((i for i in items if i.kind == "hotel" and i.name == stop.get("hotel")), None) or \
            next((i for i in items if i.kind == "hotel" and i.stop == stop["stop"]), None)
        if hotel:
            valid = hotel.valid_until is None or hotel.valid_until >= today
            if not valid:
                calc.warnings.append(f"Prijs van {hotel.name} is verlopen ({hotel.valid_until}); vraag een nieuwe prijs op")
            calc.lines.append(Line("hotel", f"{hotel.name} ({stop['stop']})", rooms * stop["nights"], hotel.cost_eur, hotel.id, valid))
        transfer = next((i for i in items if i.kind == "transfer" and i.stop == stop["stop"]), None)
        if transfer:
            calc.lines.append(Line("transfer", transfer.name, 1, transfer.cost_eur, transfer.id))
    youngest = min(child_ages) if child_ages else 18
    for name in excursions or []:
        ex = next((i for i in items if i.kind == "excursion" and i.name == name), None)
        if not ex:
            continue
        if ex.min_child_age and youngest < ex.min_child_age:
            calc.warnings.append(f"{ex.name} is vanaf {ex.min_child_age} jaar; het jongste kind is {youngest}")
            continue
        calc.lines.append(Line("excursion", ex.name, persons, ex.cost_eur, ex.id))
    return calc


def price_version(s: Session, destination: str) -> str:
    """Hash of the price lines for a destination: changes whenever a price or validity date changes."""
    import hashlib
    rows = s.scalars(select(PriceItem).where(PriceItem.destination == destination).order_by(PriceItem.id)).all()
    raw = "|".join(f"{r.id}:{r.cost_eur}:{r.valid_until}" for r in rows)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def quote(s: Session, destination: str, route: list[dict], adults: int, child_ages: list[int],
          excursions: list[str] | None = None, request_id: str | None = None) -> dict:
    """The calculation service: price a route and store the quote with its price table version."""
    from .db import Quote
    calc = calculate(s, destination, route, adults, child_ages, excursions).as_dict()
    q = Quote(request_id=request_id, destination=destination, price_version=price_version(s, destination),
              sell_eur=calc["sell_eur"], data=calc)
    s.add(q)
    s.flush()
    return calc | {"quote_id": q.id, "price_version": q.price_version}
