"""Read a supplier hotel rate sheet (one tab per city, per hotel: rooms, extra beds, mandatory and additional
services, prices per night in the supplier's currency).

The layout this reads is the export most ground agents in the region send: column A the hotel name and stars,
B the contract, C the room or service text, F minimum nights, G occupancy (SGL, DBL, TPL, 1ADL...), H one or
more periods (dd.mm.yyyy - dd.mm.yyyy), I the days of the week, J the price. A room's text carries its board
("Deluxe, Bed and Breakfast") and its maximum occupancy ("Max pax: - 3 Adults - 2 Adults 2 Children").

The sheet is commercial data from a supplier: it stays outside the repository (BRAIN_RATES points at it).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

SECTIONS = {"Room details": "room", "Extra bed": "extra", "Mandatory services": "mandatory",
            "Additional services": "additional", "Cancellation policy": "cancel"}
DAYS = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}
OCCUPANCY = {"SGL": 1, "DBL": 2, "TPL": 3, "QUAD": 4, "4ADL": 4, "1ADL": 1, "2ADL": 2, "3ADL": 3}
_PERIOD = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2})\.(\d{2})\.(\d{4})")
_PAX = re.compile(r"(\d+)\s+Adults?(?:\s+(\d+)\s+Child(?:ren)?)?", re.IGNORECASE)


@dataclass
class Rate:
    occupancy: str
    min_nights: int
    periods: list[tuple[date, date]]
    days: frozenset[int]
    price: float

    def applies(self, night: date) -> bool:
        return night.weekday() in self.days and any(a <= night <= b for a, b in self.periods)


@dataclass
class Room:
    name: str
    board: str
    max_pax: list[tuple[int, int]]  # (adults, children) combinations the room takes
    rates: list[Rate] = field(default_factory=list)

    def fits(self, adults: int, children: int) -> bool:
        if not self.max_pax:  # not stated: trust the occupancy codes
            return adults + children <= max((OCCUPANCY.get(r.occupancy, 1) for r in self.rates), default=0)
        return any(adults <= a and adults + children <= a + c for a, c in self.max_pax)


@dataclass
class Service:
    label: str
    section: str               # extra | mandatory | additional
    who: str                   # adult | child | any
    per_night: bool
    per_person: bool
    applies_to: str            # "ALL" or room names
    rates: list[Rate] = field(default_factory=list)

    def price_on(self, night: date) -> float | None:
        hit = [r.price for r in self.rates if r.applies(night)]
        return hit[0] if hit else None

    def for_room(self, room: str) -> bool:
        return self.applies_to.upper() == "ALL" or room.lower() in self.applies_to.lower()


@dataclass
class Hotel:
    city: str
    name: str
    stars: str
    contract: str
    rooms: list[Room] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)


def _periods(text) -> list[tuple[date, date]]:
    out = []
    for m in _PERIOD.finditer(str(text or "")):
        d1, m1, y1, d2, m2, y2 = map(int, m.groups())
        out.append((date(y1, m1, d1), date(y2, m2, d2)))
    return out


def _days(text) -> frozenset[int]:
    t = str(text or "")
    if not t or "All days" in t:
        return frozenset(range(7))
    return frozenset(DAYS[d] for d in re.findall(r"\b(Mo|Tu|We|Th|Fr|Sa|Su)\b", t))


def _price(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _int(v, default=1) -> int:
    try:
        return int(float(str(v)))
    except (TypeError, ValueError):
        return default


def _room(text: str) -> Room:
    lines = [x.strip(" -") for x in str(text).splitlines() if x.strip()]
    head = lines[0] if lines else str(text)
    name, _, board = head.partition(",")
    pax = [(int(a), int(c or 0)) for a, c in _PAX.findall("\n".join(lines[1:]))]
    return Room(name=name.strip(), board=board.strip(), max_pax=pax)


def _service(text: str, section: str) -> Service:
    t = str(text)
    head = t.splitlines()[0]
    applies = re.search(r"Applicable for:\s*(.+)", t)
    low = t.lower()
    h = head.lower()
    who = "infant" if "infant" in h else ("child" if "child" in h else ("adult" if "adult" in h else "any"))
    return Service(label=head.strip(), section=section, who=who, per_night="per night" in low,
                   per_person="per person" in low, applies_to=(applies.group(1).strip() if applies else "ALL"))


def read_city(ws, city: str) -> list[Hotel]:
    """One city tab: every hotel with its rooms, prices and services."""
    hotels: list[Hotel] = []
    hotel = section = None
    current = None   # the Room or Service the next price rows belong to
    occ = None
    for row in ws.iter_rows(values_only=True):
        row = list(row) + [None] * (10 - len(row))
        a, b, c, _, _, f, g, h, i, j = row[:10]
        if a and str(a).strip() != "Hotel name":
            name, _, stars = str(a).partition("\n")
            hotel = Hotel(city=city, name=name.strip(), stars=stars.strip(), contract=str(b or "").strip())
            hotels.append(hotel)
            section = current = None
        elif b and hotel is not None and str(b).strip() != "Contract name":
            # a further contract for the same hotel (a promotion, or prices for other markets)
            hotel = Hotel(city=city, name=hotel.name, stars=hotel.stars, contract=str(b).strip())
            hotels.append(hotel)
            section = current = None
        if hotel is None:
            continue
        if c and str(c).strip() in SECTIONS:
            section = SECTIONS[str(c).strip()]
            current = None
            continue
        if section in (None, "cancel"):
            continue
        if c:
            if section == "room":
                current = _room(c)
                hotel.rooms.append(current)
            else:
                current = _service(c, section)
                hotel.services.append(current)
            occ = None
        if current is None:
            continue
        if g:
            occ = str(g).strip()
        price = _price(j)
        periods = _periods(h)
        if price is None or not periods:
            continue
        if section == "room" and price <= 0:  # "on request": no price to calculate with
            continue
        current.rates.append(Rate(occupancy=occ or "", min_nights=_int(f), periods=periods, days=_days(i), price=price))
    return hotels


class RateSheet:
    """The whole workbook, read one city at a time and kept in memory."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        from openpyxl import load_workbook
        self._wb = load_workbook(self.path, read_only=True)
        self.cities = [s.title.strip() for s in self._wb.worksheets if s.title.strip() not in ("Info", "Blad1")]
        self._cache: dict[str, list[Hotel]] = {}
        info = self._wb["Info"] if "Info" in self._wb.sheetnames else None
        self.currency = "THB"
        self.created = None
        if info is not None:
            for row in info.iter_rows(max_row=5, values_only=True):
                if row and row[0] == "Currency" and row[1]:
                    self.currency = str(row[1]).strip()
                if row and row[0] == "Date created" and row[1]:
                    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", str(row[1]).strip())
                    self.created = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None

    def city(self, name: str) -> list[Hotel]:
        key = next((c for c in self.cities if c.lower() == name.strip().lower()), None)
        if key is None:
            raise KeyError(f"No tab for {name!r}. Cities in the sheet: {', '.join(self.cities)}")
        if key not in self._cache:
            ws = next(s for s in self._wb.worksheets if s.title.strip() == key)
            self._cache[key] = read_city(ws, key)
        return self._cache[key]

    def contracts(self, city: str, name: str, market: str = "Europe") -> list[Hotel]:
        """Every contract of one hotel that is valid for the client's market."""
        hotels = self.city(city)
        n = name.strip().lower()
        names = sorted({h.name for h in hotels})
        hit = [x for x in names if x.lower() == n] or [x for x in names if n in x.lower()]
        if not hit:
            raise KeyError(f"No hotel like {name!r} in {city}.")
        if len(hit) > 1:
            raise KeyError(f"{name!r} matches several hotels in {city}: {', '.join(hit[:6])}")
        return [h for h in hotels if h.name == hit[0] and market_ok(h.contract, market)]

    def hotel_names(self, city: str) -> list[str]:
        return sorted({h.name for h in self.city(city)})


def market_ok(contract: str, market: str = "Europe") -> bool:
    """A contract applies when it names the market or is worldwide without excluding it."""
    c = contract.lower()
    m = market.lower()
    if m in c and not re.search(r"ex\.[^)]*" + re.escape(m), c):
        return True
    if "worldwide" in c:
        return not re.search(r"ex\.[^)]*" + re.escape(m), c)
    return False


@lru_cache(maxsize=4)
def open_sheet(path: str) -> RateSheet:
    return RateSheet(path)
