"""Build the synthetic tenant (by default the invented Wolkenwaai Reizen): staff, families, partners, prices, past proposals,
knowledge, an inbox and some trips already in progress. Deterministic for a given seed."""
from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy import select

from .. import db
from ..db import (Draft, Employee, Family, KnowledgeItem, Mail, Partner, PartnerRequest,
                  PastProposal, PriceItem, Team, TripRequest)
from .world import BACK_OFFICE, CITIES, DESTINATIONS, FIRST_NAMES, STAFF, SURNAMES, TEAMS, WISHES
from ..clock import utcnow
from ..tenant import tenant

MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
          "november", "december"]
NUM_WORDS = {2: "twee", 3: "drie", 4: "vier", 5: "vijf", 6: "zes"}


def slug(s: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in s).strip("-").replace("--", "-")


def team_for(dest: str) -> str:
    return next(t for t, (_, dests) in TEAMS.items() if dest in dests)


def route_for(rng: random.Random, dest: str, days: int) -> list[dict]:
    """Pick stops that fit the trip length. Two nights go to the flights; spare nights are spread
    over the stops, with a bit more at the end (often the beach)."""
    stops = DESTINATIONS[dest]["stops"]
    nights_left = days - 2
    chosen = [stops[0]] + [s for s in stops[1:-1] if rng.random() < 0.75] + [stops[-1]]
    while len(chosen) > 2 and sum(max(1, n - 1) for _, n, _, _ in chosen) > nights_left:
        chosen.pop(rng.randrange(1, len(chosen) - 1))
    route = [{"stop": st, "nights": n, "hotel": hotels[0]} for st, n, hotels, _ in chosen]
    total = sum(r["nights"] for r in route)
    i = 0
    while total > nights_left:  # too long: trim, never below one night
        r = route[1 + i % (len(route) - 1)] if len(route) > 1 else route[0]
        if r["nights"] > 1:
            r["nights"] -= 1
            total -= 1
        i += 1
    order = list(range(len(route) - 1, 0, -1)) or [0]
    i = 0
    while total < nights_left:  # too short: add, starting at the end
        route[order[i % len(order)]]["nights"] += 1
        total += 1
        i += 1
    return route


def past_proposal_text(dest: str, route: list[dict], party: str, rng: random.Random) -> str:
    d = DESTINATIONS[dest]
    opener = rng.choice([
        f"Wat leuk dat jullie met {party} naar {d['nl']} willen!",
        f"Dank voor jullie aanvraag. {d['nl']} is een prachtige keuze voor {party}.",
        f"Wat een mooi plan: {d['nl']} met {party}.",
    ])
    lines = [opener, "", "Ik heb een route gemaakt met een rustig tempo, zodat er tijd is om echt ergens te zijn.", ""]
    for r in route:
        stop = next(s for s in d["stops"] if s[0] == r["stop"])
        lines.append(f"{r['stop']} ({r['nights']} nachten): jullie slapen in {r['hotel']}. Een aanrader: {stop[3][0].lower()}.")
    lines += ["", f"De beste reistijd is {d['best']}.", "Laat gerust weten wat jullie ervan vinden, dan passen we het samen aan.",
              "", "Hartelijke groet,"]
    return "\n".join(lines)


def build(seed: int = 42, n_families: int = 200, hard: bool = True) -> dict:
    rng = random.Random(seed)
    today = utcnow().replace(hour=9, minute=0, second=0, microsecond=0)
    counts: dict[str, int] = {}
    db.create_all(drop=True)
    with db.session() as s:
        # Teams and staff
        for tid, (name, dests) in TEAMS.items():
            s.add(Team(id=tid, name=name, destinations=dests))
        s.flush()
        employees = []
        for tid, staff in STAFF.items():
            employees.append(Employee(id=slug(staff["lead"]), name=staff["lead"], role="team_lead", team_id=tid))
            for n in staff["specialists"]:
                employees.append(Employee(id=slug(n), name=n, role="specialist", team_id=tid))
        for n in BACK_OFFICE:
            employees.append(Employee(id=slug(n), name=n, role="back_office", team_id=None))
        employees.append(Employee(id="noor-visser", name="Noor Visser", role="content", team_id=None))
        employees.append(Employee(id="myt-beheer", name="Myt beheer", role="admin", team_id=None))
        for e in employees:
            e.email = f"{e.id}@{tenant().own_domains[0]}"
        s.add_all(employees)
        s.flush()
        specialists = {t: [e for e in employees if e.role == "specialist" and e.team_id == t] for t in TEAMS}

        # Partners and price list
        partners: dict[str, list[Partner]] = {}
        price_n = 0
        for dest, d in DESTINATIONS.items():
            pname, kind = d["partner"]
            local = Partner(id=slug(pname), name=pname, kind=kind, destination=dest,
                            email=f"reservations@{slug(pname)}.example", avg_reply_days=round(rng.uniform(0.5, 3.5), 1),
                            reliability=round(rng.uniform(0.75, 0.98), 2))
            partners[dest] = [local]
            s.add(local)
            s.flush()
            for stop, _, hotels, excursions in d["stops"]:
                for h in hotels:
                    hp = Partner(id=slug(h), name=h, kind="hotel", destination=dest, email=f"booking@{slug(h)}.example",
                                 avg_reply_days=round(rng.uniform(0.5, 4.0), 1), reliability=round(rng.uniform(0.6, 0.97), 2))
                    partners[dest].append(hp)
                    s.add(hp)
                    s.flush()
                    price_n += 1
                    s.add(PriceItem(id=f"p{price_n}", destination=dest, kind="hotel", name=h, stop=stop, unit="per_room_night",
                                    cost_eur=rng.choice([75, 95, 120, 150, 180, 220, 260]) * (1.6 if dest in ("tanzania", "south-africa") and "Camp" in h else 1), partner_id=hp.id,
                                    valid_until=(today + timedelta(days=rng.choice([-20, 60, 120, 240]))).date()))
                for ex in excursions:
                    price_n += 1
                    min_age = 0
                    if "vanaf" in ex:
                        min_age = int("".join(ch for ch in ex.split("vanaf")[1] if ch.isdigit()) or 0)
                    s.add(PriceItem(id=f"p{price_n}", destination=dest, kind="excursion", name=ex, stop=stop, unit="per_person",
                                    cost_eur=rng.choice([15, 25, 35, 45, 60, 80]), partner_id=local.id, min_child_age=min_age))
                price_n += 1
                s.add(PriceItem(id=f"p{price_n}", destination=dest, kind="transfer", name=f"Prive transfer naar {stop}", stop=stop,
                                unit="per_trip", cost_eur=rng.choice([40, 60, 90, 120]), partner_id=local.id))
            price_n += 1
            s.add(PriceItem(id=f"p{price_n}", destination=dest, kind="flight", name=f"Retourvlucht Amsterdam {d['airport']}",
                            unit="per_person", cost_eur=d["flight_pp"]))
        air = Partner(id="skybridge-fares", name="SkyBridge Fares", kind="airline", destination="*",
                      email="groups@skybridge.example", avg_reply_days=1.0, reliability=0.95)
        s.add(air)
        counts["partners"] = sum(len(v) for v in partners.values()) + 1
        counts["price_items"] = price_n

        # Families
        families = []
        for i in range(n_families):
            sur = rng.choice(SURNAMES)
            first = rng.choice(FIRST_NAMES)
            kids = sorted(rng.choice([[rng.randint(2, 6)], [rng.randint(4, 9), rng.randint(7, 13)],
                                      [rng.randint(3, 8), rng.randint(6, 12), rng.randint(10, 16)],
                                      [rng.randint(9, 17), rng.randint(12, 18)]]))
            fam = Family(id=f"fam{i + 1:03d}", surname=sur, contact_name=f"{first} {sur}",
                         email=f"{first.lower()}.{slug(sur)}{i}@example.org", adults=rng.choice([2, 2, 2, 1]),
                         child_ages=kids, child_birth_years=__import__("brain.family", fromlist=["x"]).birth_years(kids),
                         city=rng.choice(CITIES),
                         past_destinations=rng.sample(list(DESTINATIONS), k=rng.choice([0, 0, 1, 1, 2])))
            families.append(fam)
        s.add_all(families)
        s.flush()
        counts["families"] = len(families)

        # Past proposals: the examples for routes and house voice
        pp = []
        for i in range(80):
            dest = rng.choice(list(DESTINATIONS))
            days = rng.choice([15, 18, 21, 21, 24])
            route = route_for(rng, dest, days)
            kids = rng.choice(["twee kinderen", "drie kinderen", "een tiener en een kind", "jullie zoon"])
            pp.append(PastProposal(id=f"pp{i + 1:03d}", destination=dest, days=days, party=kids, route=route,
                                   text=past_proposal_text(dest, route, kids, rng),
                                   price_pp_eur=round(rng.uniform(2100, 4200), -1), booked=rng.random() < 0.55))
        s.add_all(pp)
        counts["past_proposals"] = len(pp)

        # Knowledge, with owners, approval and review dates
        k = []
        leads = {t: next(e for e in employees if e.role == "team_lead" and e.team_id == t) for t in TEAMS}

        def add_k(kid, title, body, dest, topic, owner, approved=True, review_days=180):
            k.append(KnowledgeItem(id=kid, title=title, body=body, destination=dest, topic=topic, owner_id=owner.id,
                                   status="approved" if approved else "proposed",
                                   approved_by=leads[owner.team_id or "asia"].name if approved else None,
                                   approved_at=today - timedelta(days=rng.randint(5, 300)) if approved else None,
                                   review_by=(today + timedelta(days=review_days)).date()))

        bo = [e for e in employees if e.role == "back_office"]
        for dest, d in DESTINATIONS.items():
            t = team_for(dest)
            owner = rng.choice(specialists[t])
            add_k(f"k-{dest}-season", f"Beste reistijd {d['nl']}",
                  f"De beste reistijd voor {d['nl']} is {d['best']}. Regen: {d['rain']}.", dest, "season", owner)
            for stop, nights, hotels, excursions in d["stops"]:
                fam_ex = ", ".join(e for e in excursions)
                add_k(f"k-{dest}-{slug(stop)}", f"{stop} met kinderen",
                      f"In {stop} adviseren we {nights} nachten. Hotels die we kennen: {', '.join(hotels)}. "
                      f"Wat gezinnen leuk vinden: {fam_ex}.", dest, "family", rng.choice(specialists[t]),
                      approved=rng.random() < 0.85, review_days=rng.choice([-30, 90, 200, 300]))
            pname = d["partner"][0]
            add_k(f"k-{dest}-partner", f"Lokale partner {d['nl']}",
                  f"Onze lokale partner in {d['nl']} is {pname}. Zij regelen transfers, gidsen en excursies. "
                  f"Vraag beschikbaarheid altijd met reisdata, aantal personen en leeftijden van de kinderen.",
                  dest, "partner", rng.choice(bo))
            add_k(f"k-{dest}-entry", f"Inreisregels {d['nl']} (placeholder)",
                  f"PLACEHOLDER: inreisregels voor {d['nl']} worden niet in de sandbox gevuld. Verwijs altijd naar de "
                  f"officiele bron (Nederlandse overheid en ambassade) en controleer voor elke reis.", dest, "entry", owner,
                  review_days=30)
        policy = [
            ("k-policy-payment", "Betaaltermijnen", "Bij boeking betaalt de klant een aanbetaling van 30 procent. Het restant "
             "betaalt de klant uiterlijk zes weken voor vertrek. Geldig vanaf 1 juli 2026. (Sandbox voorbeeld, niet de echte voorwaarden.)"),
            ("k-policy-payment-2025", "Betaaltermijnen (versie 2025)", "Bij boeking betaalt de klant een aanbetaling van 25 procent. Het restant "
             "betaalt de klant uiterlijk acht weken voor vertrek. (Sandbox voorbeeld, oude versie.)"),
            ("k-policy-margins", "Marge-afspraken", "Standaard marges: hotels 22 procent, excursies 25 procent, transfers 20 procent, "
             "vluchten 6 procent. Afwijken alleen met akkoord van de teamleider. (Sandbox voorbeeld, intern.)"),
            ("k-policy-changes", "Wijzigen na boeking", "Een wijziging na boeking kan zolang partners dat toelaten. We rekenen "
             "wijzigingskosten als de partner die rekent. (Sandbox voorbeeld.)"),
            ("k-policy-insurance", "Reisverzekering", "We raden een doorlopende reisverzekering en annuleringsverzekering aan. "
             "(Sandbox voorbeeld.)"),
            ("k-voice", "Huisstijl in mails", "Schrijf persoonlijk en warm, spreek gezinnen aan met jullie, noem de kinderen bij "
             "hun leeftijd waar het helpt, houd zinnen kort, geen uitroeptekens behalve in de opening, sluit af met een "
             "uitnodiging om samen aan te passen."),
        ]
        for kid, title, body in policy:
            k.append(KnowledgeItem(id=kid, title=title, body=body, destination=None,
                                   topic="house_voice" if kid == "k-voice" else "policy", owner_id=rng.choice(bo).id,
                                   status="approved", approved_by="Marloes Kuiper", approved_at=today - timedelta(days=40),
                                   review_by=(today + timedelta(days=150)).date(),
                                   valid_from=date(2026, 7, 1) if kid == "k-policy-payment" else (date(2025, 1, 1) if kid.endswith("2025") else None),
                                   valid_to=date(2026, 6, 30) if kid.endswith("2025") else None,
                                   roles=["back_office", "team_lead", "content"] if kid == "k-policy-margins" else None))
        s.add_all(k)
        counts["knowledge"] = len(k)

        # Inbox
        mails = []
        mid = 0

        def mail(**kw):
            nonlocal mid
            mid += 1
            m = Mail(id=f"m{mid:04d}", **kw)
            mails.append(m)
            return m

        for i in range(70):
            fam = rng.choice(families)
            dest = rng.choice(list(DESTINATIONS))
            d = DESTINATIONS[dest]
            days = rng.choice([14, 18, 21, 21, 24])
            month = rng.choice(MONTHS)
            budget = rng.choice([None, 9000, 12000, 15000, 18000, 22000])
            wishes = rng.sample(WISHES, k=2)
            urgent = rng.random() < 0.12
            n_kids = len(fam.child_ages)
            kids_txt = " en ".join(str(a) for a in fam.child_ages)
            party = rng.choice([
                f"We zijn met {fam.adults} volwassenen en {n_kids} kinderen ({kids_txt} jaar).",
                f"Wij ({'twee ouders' if fam.adults == 2 else 'een ouder'}) reizen met onze kinderen van {kids_txt} jaar.",
                f"Gezin met {NUM_WORDS.get(fam.adults + n_kids, fam.adults + n_kids)} personen, kinderen zijn {kids_txt}.",
            ])
            dur = rng.choice([f"ongeveer {days} dagen", f"{days // 7} weken" if days % 7 == 0 else f"{days} dagen", f"{days} dagen"])
            body = "\n".join([
                rng.choice(["Hallo,", f"Beste {tenant().short_name},", "Goedemiddag,"]),
                "",
                rng.choice([f"Wij willen graag in {month} naar {d['nl']}, {dur}.",
                            f"In {month} hopen we {dur} door {d['nl']} te reizen.",
                            f"We denken aan een reis naar {d['nl']} van {dur}, vertrek in {month}."]),
                party,
                f"Belangrijk voor ons: {wishes[0]} en {wishes[1]}.",
                (f"Ons budget is ongeveer {budget} euro in totaal." if budget else "Over budget hebben we nog niet goed nagedacht."),
                ("Kunnen jullie snel reageren? We willen deze week beslissen." if urgent else ""),
                "",
                f"Groet, {fam.contact_name}",
            ])
            mail(received_at=today - timedelta(hours=rng.randint(1, 72)), sender=fam.email,
                 subject=rng.choice([f"Aanvraag {d['nl']}", f"Reis {d['nl']} {month}", "Vraag over een gezinsreis", f"{d['nl']}!"]),
                 body=body, family_id=fam.id,
                 truth={"category": "new_request", "destination": dest, "adults": fam.adults, "child_ages": fam.child_ages,
                        "days": days, "month": month, "budget": budget, "urgent": urgent, "team": team_for(dest)})

        # Questions: some the brain can answer, some it cannot (these should become gaps)
        answerable = [(dest, f"Wat is de beste reistijd voor {DESTINATIONS[dest]['nl']}?", f"k-{dest}-season") for dest in DESTINATIONS]
        unanswerable = [
            ("thailand", "Kunnen we in Thailand met een kinderwagen goed uit de voeten?"),
            ("japan", "Is de JR pass in Japan nog voordelig voor een gezin?"),
            ("tanzania", "Welke malariatabletten zijn geschikt voor een kind van 4 in Tanzania?"),
            ("costa-rica", "Is autohuur met kinderzitjes in Costa Rica makkelijk te regelen?"),
            ("sri-lanka", "Kun je in Sri Lanka goed glutenvrij eten?"),
            ("vietnam", "Hoe zit het met drinkwater voor de kinderen in Vietnam?"),
        ]
        for dest, q, kid in answerable:
            fam = rng.choice(families)
            mail(received_at=today - timedelta(hours=rng.randint(1, 48)), sender=fam.email, subject="Vraag",
                 body=f"Hallo,\n\n{q}\n\nGroet, {fam.contact_name}", family_id=fam.id,
                 truth={"category": "question", "destination": dest, "knowledge_id": kid, "team": team_for(dest)})
        for dest, q in unanswerable:
            fam = rng.choice(families)
            mail(received_at=today - timedelta(hours=rng.randint(1, 48)), sender=fam.email, subject="Vraagje",
                 body=f"Beste mensen,\n\n{q}\n\nAlvast bedankt, {fam.contact_name}", family_id=fam.id,
                 truth={"category": "question", "destination": dest, "knowledge_id": None, "team": team_for(dest)})

        # Complaints (change requests are added below, linked to trips in progress)
        for i in range(5):
            fam = rng.choice(families)
            dest = rng.choice(list(DESTINATIONS))
            mail(received_at=today - timedelta(hours=rng.randint(1, 30)), sender=fam.email, subject="Niet tevreden",
                 body=rng.choice(["Hallo,\n\nWe zijn net terug en zijn echt teleurgesteld over het hotel. De kamer was vies en klein.",
                                  "Beste,\n\nDe transfer kwam niet opdagen en we hebben twee uur gewacht. Dit is echt niet goed."])
                 + f"\n\n{fam.contact_name}", family_id=fam.id,
                 truth={"category": "complaint", "destination": dest, "urgent": True, "team": team_for(dest)})
        for i in range(5):
            mail(received_at=today - timedelta(hours=rng.randint(1, 30)), sender="news@travelnewsletter.example",
                 subject=rng.choice(["Nieuwsbrief november", "Webinar: duurzame reisbranche", "Uw factuur software"]),
                 body="Dit is een nieuwsbrief. Klik hier om af te melden.", truth={"category": "other"})
        s.flush()
        s.add_all(mails)
        s.flush()
        counts["mails"] = len(mails)

        # Trips already in progress, for the follow-up agent and the partner desk
        trips = []
        for i, fam in enumerate(rng.sample(families, 30)):
            dest = rng.choice(list(DESTINATIONS))
            t = team_for(dest)
            sent = today - timedelta(days=rng.randint(1, 12))
            tr = TripRequest(id=f"r{i + 1:03d}", family_id=fam.id, team_id=t, specialist_id=rng.choice(specialists[t]).id,
                             destination=dest, days=rng.choice([18, 21, 24]), depart_month=rng.choice(MONTHS),
                             budget_eur=rng.choice([None, 12000, 16000]), wishes=rng.sample(WISHES, 2),
                             status=rng.choice(["proposal_sent", "proposal_sent", "booked", "new"]),
                             created_at=sent - timedelta(days=3), proposal_sent_at=sent,
                             last_customer_contact=sent - timedelta(days=rng.randint(0, 2)))
            trips.append(tr)
        for tr in trips:
            if tr.status == "booked":
                tr.depart_date = (today + timedelta(days=rng.choice([0, 1, 1, 2, 9, 20]))).date()
                fl = f"{rng.choice(['KL', 'TK', 'EK', 'QR', 'LH'])}{rng.randint(100, 999)}"
                tr.flights = [{"number": fl, "date": tr.depart_date.isoformat(), "from": "AMS", "to": DESTINATIONS[tr.destination]["airport"]}]
        s.add_all(trips)
        s.flush()
        pr_n = 0
        for tr in trips:
            if tr.status != "booked":
                continue
            for p in [partners[tr.destination][0]] + rng.sample(partners[tr.destination][1:], 2):
                pr_n += 1
                st = rng.choice(["waiting", "waiting", "answered", "chased", "to_send"])
                sent_at = today - timedelta(days=rng.randint(0, 7)) if st != "to_send" else None
                offer = None
                if st == "answered":
                    offer = {"price_eur": rng.choice([780, 920, 1150, 1400]), "available": rng.random() < 0.85,
                             "note": rng.choice(["Family room available", "Two separate rooms only", "Breakfast included"])}
                s.add(PartnerRequest(request_id=tr.id, partner_id=p.id,
                                     what="Room availability and price" if p.kind == "hotel" else "Transfers and excursions",
                                     status=st, sent_at=sent_at, answered_at=today if st == "answered" else None,
                                     chased_at=today - timedelta(days=1) if st == "chased" else None, offer=offer))
        # Earlier proposals for trips already sent, and change requests on some of them
        from ..pricing import calculate
        fam_by_id = {f.id: f for f in families}
        spec_name = {e.id: e.name for e in employees}
        sent_trips = []
        for tr in trips:
            if tr.status not in ("proposal_sent", "booked"):
                continue
            fam = fam_by_id[tr.family_id]
            route = route_for(rng, tr.destination, tr.days)
            youngest = min(fam.child_ages) if fam.child_ages else 18
            for r in route:
                stop = next(st for st in DESTINATIONS[tr.destination]["stops"] if st[0] == r["stop"])
                acts = [a for a in stop[3] if not ("vanaf" in a and int("".join(c for c in a.split("vanaf")[1] if c.isdigit()) or 0) > youngest)]
                r["activities"] = acts[:1]
            price = calculate(s, tr.destination, route, fam.adults, fam.child_ages, [a for r in route for a in r["activities"]]).as_dict()
            s.add(Draft(kind="proposal", request_id=tr.id, title=f"Jullie reis naar {DESTINATIONS[tr.destination]['nl']}",
                        body=past_proposal_text(tr.destination, route, "jullie kinderen", rng), data={"route": route, "price": price},
                        sources=[], status="approved", final_body=None, edit_share=round(rng.uniform(0.04, 0.45), 3),
                        created_at=tr.proposal_sent_at - timedelta(hours=20), decided_at=tr.proposal_sent_at,
                        decided_by=spec_name.get(tr.specialist_id)))
            if tr.status == "proposal_sent":
                sent_trips.append((tr, fam, route))
        n_before = len(mails)
        used = rng.sample(sent_trips, min(10, len(sent_trips)))
        for tr, fam, route in used:
            mid_stops = [r["stop"] for r in route[1:-1]] or [route[0]["stop"]]
            kind = rng.choice(["extend_beach", "extend_stop", "shorten", "skip", "dates", "train"])
            if kind == "extend_beach":
                txt, ops = "Kunnen we twee nachten langer aan het strand blijven?", [{"op": "extend_stop", "stop": route[-1]["stop"], "nights": 2}]
            elif kind == "extend_stop":
                st = rng.choice(mid_stops)
                txt, ops = f"Het voorstel ziet er mooi uit. Kunnen we een nacht langer in {st} blijven?", [{"op": "extend_stop", "stop": st, "nights": 1}]
            elif kind == "shorten":
                st = max(route, key=lambda r: r["nights"])["stop"]
                txt, ops = f"Kunnen we een nacht korter in {st}? Dan komen we beter uit met school.", [{"op": "shorten_stop", "stop": st, "nights": 1}]
            elif kind == "skip" and len(route) > 2:
                st = rng.choice(mid_stops)
                txt, ops = f"We twijfelen over {st}. Kunnen we {st} overslaan?", [{"op": "remove_stop", "stop": st, "nights": 0}]
            elif kind == "dates":
                txt, ops = "We willen graag een dag later vertrekken. Kan dat nog?", [{"op": "shift_dates", "stop": None, "nights": 0}]
            else:
                txt, ops = "In het voorstel staat een binnenlandse vlucht. Kunnen we in plaats daarvan met de trein?", [{"op": "swap_transport", "stop": None, "nights": 0}]
            mail(received_at=today - timedelta(hours=rng.randint(1, 20)), sender=fam.email, subject="Wijziging in ons voorstel",
                 body=f"Hoi,\n\n{txt}\n\nGroet, {fam.contact_name}", family_id=fam.id,
                 truth={"category": "change", "destination": tr.destination, "team": tr.team_id, "request_id": tr.id, "ops": ops})
        # Booking files, supplier invoices and partner offers as PDF attachments
        from ..files import files_dir, simple_pdf
        for tr in trips:
            if tr.status == "booked":
                tr.payment_status = rng.choice(["deposit", "deposit", "paid"])
                tr.insurance = rng.random() < 0.7
                tr.passports_checked = rng.random() < 0.6
        s.flush()
        prs_all = list(s.scalars(select(PartnerRequest)).all())
        partner_by_id = {p.id: p for v in partners.values() for p in v}
        inv_n = 0
        for pr in [p for p in prs_all if p.status == "answered" and (p.offer or {}).get("available")]:
            if rng.random() > 0.8:
                continue
            p = partner_by_id[pr.partner_id]
            inv_n += 1
            price = pr.offer["price_eur"]
            kind = rng.choices(["match", "differs", "unknown"], [0.6, 0.3, 0.1])[0]
            amount = price if kind == "match" else (round(price * rng.choice([1.08, 1.12, 0.9]), -1) if kind == "differs" else price)
            ref = tenant().reference(pr.request_id) if kind != "unknown" else f"{tenant().reference_prefix}-R9" + str(rng.randint(10, 99))
            mail(received_at=today - timedelta(hours=rng.randint(2, 60)), sender=p.email, subject=f"Invoice INV-2026-{1000 + inv_n}",
                 body=f"Dear {tenant().short_name},\n\nPlease find invoice INV-2026-{1000 + inv_n} for booking {ref}: amount EUR {amount:,.0f}. "
                      f"Payment within 30 days.\n\nKind regards,\n{p.name} accounts", partner_id=p.id,
                 truth={"category": "invoice", "expected_status": kind, "partner_request_id": pr.id})
        for pr in [p for p in prs_all if p.status in ("waiting", "chased")][:3]:
            p = partner_by_id[pr.partner_id]
            price = rng.choice([860, 1040, 1180, 1320])
            avail = rng.random() < 0.8
            ref = tenant().reference(pr.request_id)
            path = simple_pdf(files_dir() / "attachments" / f"offer_{ref}_{p.id}.pdf", f"{p.name}: offer {ref}",
                              [f"Reference: {ref}", "Room: family room for 2 adults and children", f"Available: {'yes' if avail else 'no, fully booked'}",
                               f"Total price: EUR {price:,}", "Cancellation: free until 45 days before arrival"])
            m = mail(received_at=today - timedelta(hours=rng.randint(1, 20)), sender=p.email, subject=f"RE: Availability request {ref}",
                     body=f"Dear {tenant().short_name} team,\n\nPlease find our offer for {ref} attached.\n\nRegards,\nReservations", partner_id=p.id,
                     truth={"category": "partner_reply", "partner_request_id": pr.id, "price_eur": price, "available": avail})
            m.attachments = [{"name": path.name, "path": str(path), "mime": "application/pdf"}]
        if hard:
            from .hard import add_hard_mails
            s.flush()
            spare = [t for t in sent_trips if t not in used] + [t for t in used]
            prs = list(s.scalars(select(PartnerRequest).where(PartnerRequest.status.in_(["waiting", "chased"]))).all())
            add_hard_mails(rng, families, spare, prs, {p.id: p for v in partners.values() for p in v} | {air.id: air}, mail, today)
            from .english import add_english_mails
            add_english_mails(random.Random(9), families, mail, today)  # own random stream: the rest of the world stays the same
        s.add_all(mails[n_before:])
        counts["mails"] = len(mails)
        counts["trips"] = len(trips)
        counts["partner_requests"] = pr_n
        s.commit()
        for item in s.scalars(select(KnowledgeItem)).all():
            if item.roles is None:
                item.roles = ["specialist", "back_office", "team_lead", "content"]
        s.commit()
        from ..knowledge import vault
        import shutil
        shutil.rmtree(vault.vault_dir(), ignore_errors=True)
        counts["vault_notes"] = vault.export_from_db(s)
        counts["reindex"] = vault.reindex(s)
        db.assert_synthetic_only(s)
    return counts

