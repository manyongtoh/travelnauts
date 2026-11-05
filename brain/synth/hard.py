"""The harder test set: mails written the way people actually write.

Mixed Dutch and English, numbers in words, misspelled countries, places instead of countries, school
holidays instead of months, budgets as "15k", several questions in one mail, partner replies, out of
office replies, complaints while travelling, signatures with personal data, forwarded threads.

Each mail has ground truth. Where more than one answer is fair (for example "zomervakantie" can be
July or August) the truth lists every acceptable value under "accept". These mails are NOT used to
build the stand-in model's rules, so its score here is an honest measure of how brittle rules are.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from ..tenant import fill_company, tenant

# (body template, truth). {name} {first} {sig} are filled per family.
NEW_REQUESTS = [
    ("Hi!\n\nWe'd love to visit Japan for three weeks in April with our kids (6 and 9). Budget is about 14k.\n\nThanks,\n{name}",
     {"destination": "japan", "days": 21, "month": "april", "child_ages": [6, 9], "budget": 14000}),
    ("Hallo,\n\nWij willen drie weken naar Sri Lanka in de kerstvakantie met onze twee kinderen van zes en negen.\n\nGroetjes, {first}",
     {"destination": "sri-lanka", "days": 21, "month": "december", "child_ages": [6, 9], "budget": None}),
    ("Goedemiddag,\n\nWe willen graag naar Tailand in de meivakantie, ongeveer 16 dagen. Onze dochter (4) en zoon (8) gaan mee.\n\n{name}",
     {"destination": "thailand", "days": 16, "month": "mei", "child_ages": [4, 8], "budget": None}),
    ("Beste,\n\nZuid Afrika, zomervakantie, 3 weken, kinderen: 5, 8 en 12 jaar. Budget €18.000.\n\nMvg,\n{name}",
     {"destination": "south-africa", "days": 21, "accept": {"month": ["juli", "augustus"]}, "child_ages": [5, 8, 12], "budget": 18000}),
    ("Hoi %COMPANY%!\n\nWe dromen al jaren van Bali. Herfstvakantie dit jaar lukt niet meer, dus volgend jaar oktober, twee weken. Kids zijn 10 en 13.\n\nLiefs, {first}",
     {"destination": "indonesia", "days": 14, "month": "oktober", "child_ages": [10, 13], "budget": None}),
    ("Hallo,\n\nKaapstad en daarna Kruger, dat lijkt ons wat. In februari, zo'n 18 dagen. Wij met z'n vieren, de meiden zijn 7 en 11.\nBudget tussen de 12 en 14 duizend.\n\n{name}",
     {"destination": "south-africa", "days": 18, "month": "februari", "child_ages": [7, 11], "accept": {"budget": [12000, 13000, 14000]}}),
    ("Dear %COMPANY%,\n\nMy partner and I are planning Costa Rica with our son (11) for 2.5 weeks in March. We like wildlife and some adventure.\n\nBest,\n{name}",
     {"destination": "costa-rica", "accept": {"days": [17, 18]}, "month": "maart", "child_ages": [11], "budget": None}),
    ("Goeiedag,\n\nTokyo en Kyoto met kinderen van 9 en 14, na Pasen, ongeveer 20 dagen. Wat kost zoiets?\n\n{name}",
     {"destination": "japan", "days": 20, "month": "april", "child_ages": [9, 14], "budget": None}),
    ("Hoi,\n\nZanzibar met een paar dagen safari ervoor! Augustus, 15 dagen, kinderen 8 en 10. 15k max.\n\n{first}",
     {"destination": "tanzania", "days": 15, "month": "augustus", "child_ages": [8, 10], "budget": 15000}),
    ("Hallo,\n\nWe twijfelen tussen Thailand of Vietnam. Januari, 3 weken. Kinderen 5 en 7. Wat raden jullie aan?\n\nGroet, {name}",
     {"accept": {"destination": ["thailand", "vietnam"]}, "days": 21, "month": "januari", "child_ages": [5, 7], "budget": None}),
    ("Beste %COMPANY%,\n\nVolgend jaar in juli willen we met onze drie kinderen (3, 6 en 9) naar Viëtnam. Liefst niet meer dan 18 dagen en een budget van ongeveer €16.500.\n\nMet vriendelijke groet,\n{name}\n{sig}",
     {"destination": "vietnam", "days": 18, "month": "juli", "child_ages": [3, 6, 9], "budget": 16500}),
    ("Hi there,\n\nLooking for a family trip to Tanzania (safari!) for 16 days around Christmas. Kids are 12 and 15. Budget roughly EUR 20,000.\n\nCheers,\n{name}",
     {"destination": "tanzania", "days": 16, "month": "december", "child_ages": [12, 15], "budget": 20000}),
    ("Hallo,\n\n---------- Doorgestuurd bericht ----------\nVan: {name}\nOnderwerp: reis\n\nKunnen jullie iets maken voor Costa-Rica? Wij gaan in november, 2 weken, met kinderen van 4 en 6.\n\n{sig}",
     {"destination": "costa-rica", "days": 14, "month": "november", "child_ages": [4, 6], "budget": None}),
    ("Hoi,\n\nWij (2 volwassenen + 1 kind van 2) willen in maart naar Ubud en daarna het strand op Bali. Twee weken.\n\n{first}",
     {"destination": "indonesia", "days": 14, "month": "maart", "child_ages": [2], "budget": None}),
    ("Beste,\n\nIk zag jullie reis Japan met kinderen. Wij willen dat ook, 24 dagen in oktober, met Floor (8) en Sem (12).\n\nGroet,\n{name}",
     {"destination": "japan", "days": 24, "month": "oktober", "child_ages": [8, 12], "budget": None}),
]

QUESTIONS = [
    ("Hallo,\n\nWat is de beste tijd om naar Japan te gaan met kinderen? En is het in de zomer erg heet?\n\n{first}",
     {"destination": "japan", "knowledge_id": "k-japan-season"}),
    ("Hi,\n\nWhen is the best time to visit Costa Rica?\n\nThanks, {first}",
     {"destination": "costa-rica", "knowledge_id": "k-costa-rica-season"}),
    ("Hoi,\n\nHoe zit het met de betaling, moet alles in een keer?\n\n{first}",
     {"destination": None, "knowledge_id": "k-policy-payment"}),
    ("Beste,\n\nHebben jullie ook reizen naar IJsland?\n\n{name}",
     {"destination": None, "knowledge_id": None}),
    ("Hallo,\n\nIs het in Tanzania veilig met kleine kinderen in een tentenkamp?\n\n{first}",
     {"destination": "tanzania", "knowledge_id": None}),
]

CHANGES = [  # filled against a real route: {last} {mid} {long}
    ("Hi,\n\nCould we stay two more nights at the beach?\n\nThanks, {first}", "extend_beach"),
    ("Hoi,\n\nMag {mid} eruit? Dan hebben we meer rust.\n\n{first}", "skip"),
    ("Hallo,\n\n1 nachtje extra in {mid} graag, de rest is perfect!\n\n{first}", "extend_mid1"),
    ("Beste,\n\nWe vinden {long} aan de lange kant. Een nacht minder daar?\n\n{first}", "shorten_long"),
    ("Hoi,\n\nIs het mogelijk om in plaats van het vliegtuig de nachttrein te nemen?\n\n{first}", "train"),
]

PARTNER_REPLIES = [
    "Dear %COMPANY% team,\n\nWe confirm availability for your request {ref}. Family room, breakfast included, EUR 940.\n\nKind regards,\nReservations",
    "Hello,\n\nUnfortunately we are fully booked on those dates for {ref}. We can offer the week after.\n\nBest regards",
    "Dear team,\n\nThank you for your request {ref}. Please find our offer attached: two connecting rooms, EUR 1,180.\n\nWarm regards",
    "Hi,\n\nRe {ref}: transfers and the guided tour are confirmed for the requested dates.\n\nRegards,\nOperations",
]

COMPLAINTS = [
    ("We staan nu op het vliegveld en de transfer is er niet!! Niemand neemt op. Wat moeten we doen?\n\n{first}", True),
    ("Hi, the hotel in our itinerary is under construction, very noisy and the pool is closed. Very disappointed.\n\n{name}", True),
    ("Hallo,\n\nHet is allemaal prima verlopen hoor, maar ik wil wel even kwijt dat de gids in Kandy erg laat was.\n\n{first}", False),
]

OTHER = [
    ("Afwezig: Re: uw reis", "Ik ben afwezig tot en met 12 november en lees mijn mail niet. Voor dringende zaken: bel kantoor."),
    ("Factuur 2026-1187", "Dear %COMPANY%, please find attached invoice 2026-1187 for transfers in October. Payment within 30 days."),
    ("You won a free cruise!", "Click here to claim your free cruise for 2 persons. Limited offer."),
]


def add_hard_mails(rng: random.Random, families: list, trips_with_routes: list, partner_requests: list, partners: dict,
                   mail, today: datetime) -> int:
    n = 0
    sig = lambda f: f"{f.contact_name}\n{rng.choice(['Dorpsstraat', 'Kerklaan', 'Molenweg'])} {rng.randint(1, 120)}\n{rng.randint(1000, 9999)} AB {f.city}\n06-{rng.randint(10000000, 99999999)}"

    def fill(t, f):
        return t.format(name=f.contact_name, first=f.contact_name.split()[0], sig=sig(f))

    for body, truth in NEW_REQUESTS:
        f = rng.choice(families)
        mail(received_at=today - timedelta(hours=rng.randint(1, 48)), sender=f.email, subject=rng.choice(["Reis", "Vraag", "Trip", "Aanvraag", ""]),
             body=fill(body, f), family_id=f.id, truth={"set": "hard", "category": "new_request", **truth})
        n += 1
    for body, truth in QUESTIONS:
        f = rng.choice(families)
        mail(received_at=today - timedelta(hours=rng.randint(1, 48)), sender=f.email, subject="Vraag",
             body=fill(body, f), family_id=f.id, truth={"set": "hard", "category": "question", **truth})
        n += 1
    for (body, kind), (tr, f, route) in zip(CHANGES, trips_with_routes):
        mids = [r["stop"] for r in route[1:-1]] or [route[0]["stop"]]
        longest = max(route, key=lambda r: r["nights"])["stop"]
        ops = {"extend_beach": [{"op": "extend_stop", "stop": route[-1]["stop"], "nights": 2}],
               "skip": [{"op": "remove_stop", "stop": mids[0], "nights": 0}],
               "extend_mid1": [{"op": "extend_stop", "stop": mids[0], "nights": 1}],
               "shorten_long": [{"op": "shorten_stop", "stop": longest, "nights": 1}],
               "train": [{"op": "swap_transport", "stop": None, "nights": 0}]}[kind]
        mail(received_at=today - timedelta(hours=rng.randint(1, 12)), sender=f.email, subject="Re: jullie voorstel",
             body=body.format(first=f.contact_name.split()[0], mid=mids[0], long=longest), family_id=f.id,
             truth={"set": "hard", "category": "change", "request_id": tr.id, "destination": tr.destination, "ops": ops})
        n += 1
    for body, pr in zip(PARTNER_REPLIES, partner_requests):
        p = partners[pr.partner_id]
        mail(received_at=today - timedelta(hours=rng.randint(1, 30)), sender=p.email, subject=f"RE: Availability request {tenant().reference(pr.request_id)}",
             body=body.format(ref=tenant().reference(pr.request_id)), partner_id=p.id,
             truth={"set": "hard", "category": "partner_reply", "partner_request_id": pr.id})
        n += 1
    for body, urgent in COMPLAINTS:
        f = rng.choice(families)
        mail(received_at=today - timedelta(minutes=rng.randint(5, 600)), sender=f.email, subject=rng.choice(["!!!", "Probleem", "Feedback"]),
             body=fill(body, f), family_id=f.id, truth={"set": "hard", "category": "complaint", "urgent": urgent})
        n += 1
    for subject, body in OTHER:
        mail(received_at=today - timedelta(hours=rng.randint(1, 30)), sender={"Afwezig": "noreply@autoreply.example", "Factuur": "billing@supplier.example"}.get(subject.split()[0].rstrip(":"), "promo@cruisedeals.example"),
             subject=subject, body=body, truth={"set": "hard", "category": "invoice" if subject.startswith("Factuur") else "other"})
        n += 1
    return n


# The synthetic texts speak to the tenant by name.
NEW_REQUESTS = fill_company(NEW_REQUESTS)
QUESTIONS = fill_company(QUESTIONS)
CHANGES = fill_company(CHANGES)
PARTNER_REPLIES = fill_company(PARTNER_REPLIES)
COMPLAINTS = fill_company(COMPLAINTS)
OTHER = fill_company(OTHER)
