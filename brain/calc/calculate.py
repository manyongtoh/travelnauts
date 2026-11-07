"""A first calculation for a trip: hotels per night from the supplier's rate sheet, transfers and excursions,
flights from the booking system's quote, converted to euro, with a suggested price per person.

It does what a specialist now does by hand in the dossier spreadsheet, and says what it is unsure of. The
specialist checks and adjusts; nothing is booked or sent from here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations_with_replacement

from .rates import Hotel, RateSheet, Room

ROOM_OCCUPANCY = {"SGL": 1, "DBL": 2, "TPL": 3, "QUAD": 4, "4ADL": 4}  # people a room rate covers

UNSURE = "te controleren"


@dataclass
class Settings:
    """Every number the calculation leans on, with where it comes from."""
    rate_to_eur: float = 0.0268          # one unit of the sheet's currency in euro
    rate_source: str = "uit een bestaand dossier, nog niet uit de valutasheet"
    target_margin: float = 0.23          # (sale - purchase) / sale
    margin_source: str = "marge van één bestaand dossier"
    child_max_age: int = 11              # older children count as adults for rooms and prices
    child_age_source: str = "aanname, verschilt per hotel"
    market: str = "Europe"               # which supplier contracts apply
    one_room_first: bool = True          # a family room before two rooms, even when two are cheaper
    other_rates: dict[str, float] = field(default_factory=lambda: {"AUD": 0.5709})  # euro per unit
    other_rates_source: str = "uit een bestaand dossier"


@dataclass
class Party:
    adults: int
    children: list[int] = field(default_factory=list)  # ages on the travel date

    def split(self, child_max_age: int) -> tuple[int, int]:
        kids = [a for a in self.children if a <= child_max_age]
        return self.adults + len(self.children) - len(kids), len(kids)

    @property
    def size(self) -> int:
        return self.adults + len(self.children)

    def describe(self) -> str:
        s = f"{self.adults} volw."
        if self.children:
            s += f" en {len(self.children)} kind{'eren' if len(self.children) > 1 else ''} ({', '.join(map(str, self.children))})"
        return s


@dataclass
class Stop:
    city: str
    hotel: str
    nights: int
    room: str | None = None   # a room name to use; otherwise the cheapest that fits


@dataclass
class Item:
    """A transfer or excursion. Prices in the sheet's currency, per person, or per group when per_group."""
    label: str
    on: date | None
    adult: float
    child: float | None = None
    per_group: bool = False
    kind: str = "transfer"    # transfer | excursion
    currency: str | None = None  # None: the rate sheet's currency


@dataclass
class Flight:
    label: str
    adult_eur: float          # purchase price per adult, taxes included, from the quote
    child_eur: float | None = None
    reference: str = ""       # option or quote reference in the booking system


@dataclass
class NightLine:
    day: int
    on: date
    city: str
    hotel: str
    contract: str
    rooms: str
    price: float
    notes: list[str] = field(default_factory=list)


@dataclass
class Alternative:
    city: str
    hotel: str
    stars: str
    rooms: str
    total: float


@dataclass
class Calculation:
    party: Party
    start: date
    currency: str
    settings: Settings
    nights: list[NightLine]
    items: list[Item]
    flights: list[Flight]
    checks: list[str]
    alternatives: dict[str, list[Alternative]]

    @property
    def hotel_total(self) -> float:
        return sum(n.price for n in self.nights)

    def to_eur(self, amount: float, currency: str | None) -> float:
        if not currency or currency == self.currency:
            return amount * self.settings.rate_to_eur
        return amount * self.settings.other_rates[currency]

    def item_cost(self, it: Item) -> float:
        """What one item costs for the whole family, in its own currency."""
        a, c = self.party.split(self.settings.child_max_age)
        return it.adult if it.per_group else it.adult * a + (it.child if it.child is not None else it.adult) * c

    def item_total_eur(self, kind: str) -> float:
        return sum(self.to_eur(self.item_cost(it), it.currency) for it in self.items if it.kind == kind)

    @property
    def flight_total_eur(self) -> float:
        a, c = self.party.split(self.settings.child_max_age)
        return sum(f.adult_eur * a + (f.child_eur if f.child_eur is not None else f.adult_eur) * c for f in self.flights)

    @property
    def purchase_eur(self) -> float:
        return (self.hotel_total * self.settings.rate_to_eur + self.item_total_eur("transfer")
                + self.item_total_eur("excursion") + self.flight_total_eur)

    def price_per_person(self) -> tuple[float, float]:
        """Suggested sale price for an adult and for a child at the target margin.

        The hotels are shared equally over everyone in the room; transfers, excursions and flights per person."""
        s = self.settings
        a, c = self.party.split(s.child_max_age)
        n = max(a + c, 1)
        share = self.hotel_total * s.rate_to_eur / n
        adult = share + sum(self.to_eur(it.adult / (n if it.per_group else 1), it.currency) for it in self.items)
        child = share + sum(self.to_eur((it.adult / n) if it.per_group else (it.child if it.child is not None else it.adult), it.currency)
                            for it in self.items)
        adult += sum(f.adult_eur for f in self.flights)
        child += sum(f.child_eur if f.child_eur is not None else f.adult_eur for f in self.flights)
        k = 1 - s.target_margin
        return adult / k, child / k


def _nights(start: date, stops: list[Stop]):
    day, on = 1, start
    for st in stops:
        for _ in range(st.nights):
            yield day, on, st
            day, on = day + 1, on + timedelta(days=1)


def _beds(hotel: Hotel, room: Room, extra_kids: int, on: date) -> tuple[float | None, list[str]]:
    """Children beyond what the rate covers: the first shares a bed (often free), the rest get an extra bed."""
    def find(who, sharing):
        return [s for s in hotel.services if s.section == "extra" and s.who == who and s.for_room(room.name)
                and ("shar" in s.label.lower()) == sharing and s.price_on(on) is not None]
    share, bed_child, bed_adult = find("child", True), find("child", False), find("adult", False)
    price, notes = 0.0, []
    for i in range(extra_kids):
        if i == 0 and share:
            price += share[0].price_on(on)
            notes.append(f"kind deelt bed: {share[0].label}")
        elif bed_child:
            price += bed_child[0].price_on(on)
            notes.append(f"extra bed kind: {bed_child[0].label}")
        elif bed_adult:
            price += bed_adult[0].price_on(on)
            notes.append(f"extra bed voor kind tegen volwassenenprijs ({room.name})")
        else:
            return None, [f"geen prijs voor een extra bed in {room.name}"]
    return price, notes


def _room_night(hotel: Hotel, room: Room, adults: int, children: int, on: date) -> tuple[float | None, list[str]]:
    """One room for one night with this many people in it: the cheapest correct way to price it.

    Every rate that covers the adults is tried (DBL, TPL, a family rate), with beds for the children beyond it."""
    people = adults + children
    options = []
    for r in room.rates:
        cap = ROOM_OCCUPANCY.get(r.occupancy, 0)
        if cap < max(adults, 1) or not r.applies(on):
            continue
        extra = max(people - cap, 0)
        if extra > children:
            continue
        beds, n = _beds(hotel, room, extra, on)
        if beds is None:
            continue
        options.append((r.price + beds, r, n))
    if not options:
        return None, [f"geen prijs voor {room.name} op {on:%d-%m}"]
    price, rate, notes = min(options, key=lambda o: (o[0], -ROOM_OCCUPANCY[o[1].occupancy]))
    notes = list(notes)
    for s in hotel.services:
        if s.section != "mandatory" or not s.for_room(room.name):
            continue
        p = s.price_on(on)
        if p is None:
            continue
        if s.per_person:
            heads = children if s.who == "child" else (adults if s.who == "adult" else adults + children)
            price += p * heads
        else:
            price += p
        notes.append(f"verplicht: {s.label}")
    if rate.min_nights > 1:
        notes.append(f"minimaal {rate.min_nights} nachten")
    return price, notes


def _splits(adults: int, children: int):
    """Ways to put a family in rooms: one room, or parents and children apart, or two mixed rooms."""
    yield ((adults, children),)
    if children:
        yield ((adults, 0), (0, children))
    if adults >= 2 and children >= 1:
        yield ((adults - 1, children // 2 + children % 2), (1, children // 2))


def _best_stay(contracts: list[Hotel], nights: list[date], adults: int, children: int, room_name: str | None,
               one_room_first: bool = True):
    """Cheapest contract, room type and split that has a price for every night of the stay.

    With one_room_first a family room wins over two rooms whenever one fits."""
    best = None
    rank = lambda total, n_rooms: ((n_rooms if one_room_first else 0), total)
    for h in contracts:
        rooms = [r for r in h.rooms if not room_name or room_name.lower() in r.name.lower()]
        for split in _splits(adults, children):
            for combo in combinations_with_replacement(rooms, len(split)):
                if not all(rm.fits(a, c) for rm, (a, c) in zip(combo, split)):
                    continue
                total, per_night, notes = 0.0, [], []
                ok = True
                for on in nights:
                    night = 0.0
                    for rm, (a, c) in zip(combo, split):
                        p, n = _room_night(h, rm, a, c, on)
                        if p is None:
                            ok = False
                            break
                        night += p
                        notes += n
                    if not ok:
                        break
                    per_night.append(night)
                    total += night
                if ok and (best is None or rank(total, len(split)) < rank(best[0], best[5])):
                    label = " + ".join(f"1x {rm.name} ({a} volw.{f' {c} kind' if c else ''})" for rm, (a, c) in zip(combo, split))
                    best = (total, h, label, per_night, sorted(set(notes)), len(split))
    return best


def calculate(sheet: RateSheet, party: Party, start: date, stops: list[Stop], items: list[Item] | None = None,
              flights: list[Flight] | None = None, settings: Settings | None = None, alternatives: int = 3) -> Calculation:
    s = settings or Settings()
    adults, children = party.split(s.child_max_age)
    lines: list[NightLine] = []
    checks: list[str] = []
    alts: dict[str, list[Alternative]] = {}
    plan = list(_nights(start, stops))
    for st in stops:
        dates = [on for _, on, x in plan if x is st]
        days = [d for d, _, x in plan if x is st]
        try:
            contracts = sheet.contracts(st.city, st.hotel, s.market)
        except KeyError as e:
            checks.append(str(e).strip('"'))
            for d, on in zip(days, dates):
                lines.append(NightLine(d, on, st.city, st.hotel, "", "", 0.0, ["hotel niet in de prijzenlijst"]))
            continue
        best = _best_stay(contracts, dates, adults, children, st.room, s.one_room_first)
        if best is None:
            checks.append(f"{st.hotel}: geen kamer met een prijs voor alle nachten van {dates[0]:%d-%m} tot {dates[-1] + timedelta(days=1):%d-%m} voor {party.describe()}")
            for d, on in zip(days, dates):
                lines.append(NightLine(d, on, st.city, st.hotel, "", "", 0.0, ["geen prijs"]))
            continue
        _total, h, label, per_night, notes, _ = best
        for d, on, p in zip(days, dates, per_night):
            lines.append(NightLine(d, on, st.city, h.name, h.contract, label, p, notes))
        if "promotion" in h.contract.lower():
            checks.append(f"{h.name}: goedkoopste prijs is een promotie ({h.contract}); voorwaarden controleren")
        for n in notes:
            if n.startswith("minimaal"):
                need = int(n.split()[1])
                if st.nights < need:
                    checks.append(f"{h.name}: {n}, gepland {st.nights}")
            elif n.startswith(("geen", "extra bed voor kind")):
                checks.append(f"{h.name}: {n}")
        if children and " + " in label and "(0 volw." in label:
            checks.append(f"{h.name}: kinderen in een eigen kamer; past dat bij hun leeftijd?")
        if alternatives:
            alts[st.city] = suggest(sheet, st.city, dates, adults, children, s.market, exclude=h.name, limit=alternatives,
                                    one_room_first=s.one_room_first)
    for it in items or []:
        if it.child is None and not it.per_group and children:
            checks.append(f"{it.label}: geen kinderprijs opgegeven, volwassenenprijs gebruikt")
        if it.currency and it.currency != sheet.currency:
            if it.currency not in s.other_rates:
                raise ValueError(f"no rate to euro for {it.currency}; add it to Settings.other_rates")
            checks.append(f"koers {s.other_rates[it.currency]} per {it.currency} voor {it.label}: {UNSURE} ({s.other_rates_source})")
    if sheet.created and (start - sheet.created).days > 365:
        checks.append(f"de prijzenlijst is van {sheet.created:%d-%m-%Y}; voor deze reisdatum mogelijk verouderd")
    checks.append(f"koers {s.rate_to_eur} per {sheet.currency}: {UNSURE} ({s.rate_source})")
    checks.append(f"doelmarge {s.target_margin:.0%}: {UNSURE} ({s.margin_source})")
    checks.append(f"kinderen tot en met {s.child_max_age} jaar als kind gerekend: {UNSURE} ({s.child_age_source})")
    return Calculation(party, start, sheet.currency, s, lines, list(items or []), list(flights or []), checks, alts)


def suggest(sheet: RateSheet, city: str, dates: list[date], adults: int, children: int, market: str = "Europe",
            exclude: str = "", limit: int = 3, one_room_first: bool = True) -> list[Alternative]:
    """The cheapest other hotels in a city that fit the family for these nights."""
    out = []
    for name in sheet.hotel_names(city):
        if name == exclude:
            continue
        contracts = sheet.contracts(city, name, market)
        if not contracts:
            continue
        best = _best_stay(contracts, dates, adults, children, None, one_room_first)
        if best:
            out.append((best[5] if one_room_first else 0, best[0], Alternative(city, name, contracts[0].stars, best[2], best[0])))
    return [a for _, _, a in sorted(out, key=lambda x: (x[0], x[1]))][:limit]
