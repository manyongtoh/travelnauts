"""The stand-in model for the sandbox.

It plays the part of the language model without any network: it reads the same instructions and
CONTEXT a real model gets and returns the same typed output, built with simple rules and templates.
That lets us test the whole flow, the screens and the measurements before a real model is attached.
It does not show how good the writing will be; for that, run with BRAIN_MODEL=ollama:gemma4.
"""
from __future__ import annotations

import json
import re

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .synth.world import DESTINATIONS, WISHES
from .tenant import tenant

MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
          "november", "december"]
NUMS = {"een": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6, "zeven": 7}


def _instructions(info: AgentInfo) -> str:
    ins = info.instructions
    if isinstance(ins, (list, tuple)):
        return "\n".join(str(i) for i in ins)
    return str(ins or "")


def _context(messages: list[ModelMessage]) -> dict:
    for msg in reversed(messages):
        for part in getattr(msg, "parts", []):
            if isinstance(part, UserPromptPart) and isinstance(part.content, str) and part.content.startswith("CONTEXT:"):
                return json.loads(part.content.removeprefix("CONTEXT:"))
    return {}


# Handlers, one per task ---------------------------------------------------------------------

def triage(ctx: dict) -> dict:
    m = ctx["mail"]
    text = f"{m['subject']}\n{m['body']}"
    low = text.lower()
    dest = None
    for key, nl in ctx["destinations"].items():
        if nl.lower() in low:
            dest = key
            break
    if "news" in m["from"].lower() or "afmelden" in low:
        cat = "other"
    elif re.search(r"\b(invoice|factuur)\b", low) and not re.search(r"@example\.org|freemail", m["from"].lower()):
        cat = "invoice"
    elif re.search(rf"{tenant().ref_re.lower()}-r\d{{3,}}", low) and not re.search(r"@example\.org|freemail", m["from"].lower()):
        cat = "partner_reply"
    elif any(w in low for w in ["teleurgesteld", "niet tevreden", "echt niet goed", "kwam niet opdagen", "klacht"]):
        cat = "complaint"
    elif any(w in low for w in ["wijzig", "in het voorstel", "later vertrekken", "in plaats daarvan"]):
        cat = "change"
    elif dest and re.search(r"\b(willen|hopen|denken aan)\b", low) and re.search(r"(dagen|weken)", low):
        cat = "new_request"
    elif "?" in text:
        cat = "question"
    else:
        cat = "other"
    out: dict = {"category": cat, "confidence": 0.5 if cat == "other" and "?" in text else 0.9,
                 "destination": dest if cat not in ("other", "partner_reply", "invoice") else None,
                 "urgent": cat == "complaint" or "snel reageren" in low, "child_ages": [], "wishes": []}
    if cat == "new_request":
        ages = re.search(r"kinderen (?:\(|van |zijn )([\d en]+?)(?: jaar|\)|\.| en [a-z])", low)
        out["child_ages"] = [int(a) for a in re.findall(r"\d+", ages.group(1))] if ages else []
        if (a := re.search(r"met (\d) volwassenen", low)):
            out["adults"] = int(a.group(1))
        elif "twee ouders" in low:
            out["adults"] = 2
        elif "een ouder" in low:
            out["adults"] = 1
        elif (p := re.search(r"gezin met (\w+) personen", low)):
            w = p.group(1)
            total = int(w) if w.isdigit() else NUMS.get(w)
            out["adults"] = (total - len(out["child_ages"])) if total else None
        if (d := re.search(r"(\d+) dagen", low)):
            out["days"] = int(d.group(1))
        elif (w := re.search(r"(\d) weken", low)):
            out["days"] = int(w.group(1)) * 7
        mo = re.search(r"\b(?:in|vertrek in|rond|eind|begin) (" + "|".join(MONTHS) + r")\b", low)
        out["month"] = mo.group(1) if mo else None
        if (b := re.search(r"budget is ongeveer (\d+)", low)):
            out["budget_eur"] = float(b.group(1))
        out["wishes"] = [w for w in WISHES if w in low]
    nl = ctx["destinations"].get(dest, "") if dest else ""
    out["summary"] = {
        "new_request": f"Nieuwe aanvraag {nl}, {out.get('days') or '?'} dagen, {out.get('month') or 'maand onbekend'}",
        "change": "Wijziging in een bestaand voorstel",
        "question": f"Vraag{(' over ' + nl) if nl else ''}",
        "complaint": "Klacht, snel oppakken",
        "partner_reply": "Antwoord van een partner",
        "invoice": "Factuur van een leverancier, naar de back office",
        "other": "Geen actie nodig",
    }[cat]
    return out


def _kids(ages: list[int]) -> str:
    if not ages:
        return ""
    if len(ages) == 1:
        return f"jullie kind van {ages[0]}"
    return "de kinderen van " + ", ".join(str(a) for a in ages[:-1]) + f" en {ages[-1]}"


def first_name(name: str | None) -> str:
    """'Marieke Visser' gives 'Marieke'; an unknown name gives a greeting that still reads well."""
    return (name or "").split()[0] if (name or "").strip() else "allemaal"


def proposal(ctx: dict) -> dict:
    fam, trip, route, price = ctx["family"], ctx["trip"], ctx["route"], ctx["price"]
    first = first_name(fam["name"])
    season = next((k for k in ctx["knowledge"] if "reistijd" in k["title"].lower()), None)
    lines = [f"Beste {first},", "",
             f"Wat leuk dat jullie in {trip['month']} met {_kids(fam['child_ages'])} naar {trip['destination']} willen. "
             f"Ik heb een eerste route gemaakt van {trip['days']} dagen, met een rustig tempo.", ""]
    for r in route:
        act = r.get("activities") or []
        act_txt = f" Leuk om te doen: {', '.join(a[0].lower() + a[1:] for a in act)}." if act else ""
        lines.append(f"{r['stop']}, {r['nights']} {'nacht' if r['nights'] == 1 else 'nachten'} in {r['hotel']}.{act_txt}")
    lines.append("")
    used = []
    if season:
        lines.append(season["text"] + (" (Deze informatie checken we nog.)" if season["outdated"] else ""))
        used.append(season["id"])
    used += [k["id"] for k in ctx["knowledge"] if any(r["stop"] in k["title"] for r in route)]
    if trip.get("wishes"):
        lines.append(f"Ik heb rekening gehouden met jullie wensen: {', '.join(trip['wishes'])}.")
    eur = f"{int(price['sell_eur']):,}".replace(",", ".")
    lines.append(f"De indicatie voor deze reis is € {eur} voor het hele gezin, inclusief vluchten, "
                 f"hotels, transfers en de genoemde activiteiten."
                 + (" Een paar prijzen zijn nog niet bevestigd." if price.get("warnings") else ""))
    if trip.get("budget_eur") and price["sell_eur"] > trip["budget_eur"] * 1.05:
        lines.append("Het komt iets boven jullie budget uit. Ik denk graag mee over een paar nachten minder of eenvoudigere hotels.")
    lines += ["", "Laat ons weten wat jullie ervan vinden. We passen de route graag samen aan.", "", "Hartelijke groet,",
              ctx["specialist"]]
    return {"subject": f"Jullie reis naar {trip['destination']}: een eerste voorstel", "body": "\n".join(lines),
            "used_sources": used}


def followup(ctx: dict) -> dict:
    fam, trip = ctx["family"], ctx["trip"]
    first = first_name(fam["name"])
    body = [f"Beste {first},", "",
            f"Een tijdje geleden stuurde ik jullie een voorstel voor {trip['destination']}. Ik ben benieuwd wat jullie ervan vinden.",
            "Als er iets anders moet, pas ik de route graag aan. Bellen kan natuurlijk ook."]
    if ctx.get("knowledge"):
        body.append("Voor de beste hotels in de drukke maanden is het fijn om niet te lang te wachten.")
    body += ["", "Hartelijke groet,", ctx["specialist"]]
    return {"subject": f"Jullie voorstel voor {trip['destination']}", "body": "\n".join(body)}


def partner_request(ctx: dict) -> dict:
    t, p = ctx["trip"], ctx["partner"]
    kids = ", ".join(str(a) for a in t["child_ages"]) or "none"
    nights = f"{t['nights']} nights, " if t.get("nights") else ""
    body = (f"Dear {p['name']} team,\n\nCould you please check availability and price for the following family "
            f"(reference {ctx['reference']}):\n\n- Travel month: {t['month']}\n- {nights}{t['adults']} {'adult' if t['adults'] == 1 else 'adults'}, children aged {kids}\n"
            f"- Rooms: {t['rooms']}\n- Request: {t['what']}\n\nPlease include your cancellation terms. Thank you in advance.\n\n"
            f"Kind regards,\n{tenant().back_office_signature}")
    return {"subject": f"Availability request {ctx['reference']} ({t['month']})", "body": body}


def partner_chase(ctx: dict) -> dict:
    body = (f"Dear {ctx['partner']['name']} team,\n\nA kind reminder about our request {ctx['reference']}, sent on "
            f"{ctx['sent_at']}. Could you let us know within two working days?\n\nKind regards,\n{tenant().back_office_signature}")
    return {"subject": f"Reminder: {ctx['reference']}", "body": body}


def gds(ctx: dict) -> dict:
    f = ctx["flight"]
    phone = tenant().gds_agency_phone
    if ctx.get("system") == "galileo":
        cmds = [{"cmd": f"A{f['out']}{f['from']}{f['to']}", "explain": "Beschikbaarheid heenreis"},
                {"cmd": f"0{f['seats']}{f['class']}1", "explain": f"{f['seats']} stoelen boeken op regel 1 (na controle)"},
                {"cmd": f"A{f['back']}{f['to']}{f['from']}", "explain": "Beschikbaarheid terugreis"},
                {"cmd": f"0{f['seats']}{f['class']}1", "explain": f"{f['seats']} stoelen boeken op regel 1 (na controle)"}]
        for t in f["travellers"]:
            if t["type"] == "child":
                cmds.append({"cmd": f"N.{t['surname']}/{t['first']}CHD*C{t['age']:02d}", "explain": f"Naam kind ({t['age']} jaar)"})
            else:
                cmds.append({"cmd": f"N.{t['surname']}/{t['first']}MR", "explain": "Naam volwassene (titel controleren)"})
        cmds += [{"cmd": phone, "explain": "Telefoon kantoor"},
                 {"cmd": f"T.TAU/{f['ticket_by']}", "explain": "Uiterste ticketdatum"},
                 {"cmd": "R.AGENT", "explain": "Ontvangen van"},
                 {"cmd": "*R", "explain": "Boeking tonen ter controle"}]
    else:
        cmds = [{"cmd": f"AN{f['out']}{f['from']}{f['to']}", "explain": "Beschikbaarheid heenreis"},
                {"cmd": f"SS{f['seats']}{f['class']}1", "explain": f"{f['seats']} stoelen boeken op regel 1 (na controle)"},
                {"cmd": f"AN{f['back']}{f['to']}{f['from']}", "explain": "Beschikbaarheid terugreis"},
                {"cmd": f"SS{f['seats']}{f['class']}1", "explain": f"{f['seats']} stoelen boeken op regel 1 (na controle)"}]
        for t in f["travellers"]:
            if t["type"] == "child":
                cmds.append({"cmd": f"NM1{t['surname']}/{t['first']}(CHD)",
                             "explain": f"Naam kind ({t['age']} jaar): geboortedatum toevoegen als (CHD/DDMMMJJ)"})
            else:
                cmds.append({"cmd": f"NM1{t['surname']}/{t['first']} MR", "explain": "Naam volwassene (titel controleren)"})
        cmds += [{"cmd": phone, "explain": "Telefoon kantoor"},
                 {"cmd": f"TKTL{f['ticket_by']}", "explain": "Uiterste ticketdatum"},
                 {"cmd": "RF AGENT", "explain": "Ontvangen van"},
                 {"cmd": "RT", "explain": "Boeking tonen ter controle"}]
    return {"commands": cmds, "notes": ["Voornamen van partner en kinderen zijn placeholders: aanvullen uit het paspoort"]}


STOP = {"de", "het", "een", "en", "van", "in", "is", "op", "te", "voor", "met", "we", "wij", "jullie", "naar", "kan",
        "kunnen", "kinderen", "kind", "gezin", "jaar", "geschikt", "hoe", "wat", "welke", "zit", "nog", "goed", "zijn", "er", "uit", "voeten", "makkelijk"}


def answer(ctx: dict) -> dict:
    q = ctx["question"].lower()
    dest_words = {w for d in DESTINATIONS.values() for w in re.findall(r"[a-z]+", d["nl"].lower())}
    words = {w for w in re.findall(r"[a-z]+", q) if len(w) > 3 and w not in STOP and w not in dest_words}
    best = ctx["sources"][0]
    overlap = [w for w in words if w in (best["title"] + " " + best["text"]).lower()]
    confident = len(overlap) >= 1 and len(overlap) >= len(words) / 2
    if not confident:
        return {"answer": "Dit kan ik niet goed beantwoorden met wat het brein nu weet. Ik heb de vraag op de lijst met "
                          "kennishiaten gezet.", "cited": [], "confident": False}
    text = best["text"] + (" Let op: deze informatie moet opnieuw gecontroleerd worden." if best["outdated"] else "")
    return {"answer": text, "cited": [best["id"]], "confident": True}


NUMW = {"een": 1, "one": 1, "a": 1, "twee": 2, "two": 2, "drie": 3, "three": 3, "vier": 4, "four": 4}


def _num(w: str) -> int:
    return int(w) if w.isdigit() else NUMW.get(w, 1)


def change_plan(ctx: dict) -> dict:
    text = (ctx["mail"]["subject"] + "\n" + ctx["mail"]["body"]).lower()
    stops = [r["stop"] for r in ctx["route"]]
    def stop_in(fragment: str) -> str | None:
        if any(w in fragment for w in ("strand", "beach", "eiland", "island")):
            return stops[-1]
        return next((st for st in stops if st.lower() in fragment), None)
    ops = []
    for m in re.finditer(r"(\w+) (?:nacht|nachten|night|nights) (langer|extra|meer|korter|minder|longer|more|less|fewer)([^.?!\n]*)", text):
        n, how, rest = _num(m.group(1)), m.group(2), m.group(3)
        st = stop_in(rest) or stop_in(text[max(0, m.start() - 40):m.start()])
        ops.append({"op": "shorten_stop" if how in ("korter", "minder", "less", "fewer") else "extend_stop", "stop": st, "nights": n})
    for st in stops:
        if re.search(rf"{re.escape(st.lower())}[^.?!\n]{{0,20}}(overslaan|skippen|eruit|laten vallen)|(skip|overslaan|zonder) {re.escape(st.lower())}", text):
            ops.append({"op": "remove_stop", "stop": st, "nights": 0})
    if re.search(r"(dag|dagen|week) (later|eerder) vertrekken|later vertrekken|eerder vertrekken|leave (a day )?(later|earlier)|other dates", text):
        ops.append({"op": "shift_dates", "stop": None, "nights": 0, "note": "andere vertrekdatum"})
    if re.search(r"trein in plaats van|met de trein|by train|instead of (the )?(flight|plane)", text):
        ops.append({"op": "swap_transport", "stop": None, "nights": 0, "note": "trein in plaats van binnenlandse vlucht"})
    if not ops:
        ops.append({"op": "other", "stop": None, "nights": 0, "note": "wens niet automatisch te verwerken"})
    return {"ops": ops}


def change_reply(ctx: dict) -> dict:
    first = first_name(ctx["family"]["name"])
    lines = [f"Beste {first},", "", "Dank voor je bericht. Ik heb het voorstel aangepast:"]
    for o in ctx["applied"]:
        lines.append({"extend_stop": f"- {o['nights']} {'nacht' if o['nights'] == 1 else 'nachten'} extra in {o['stop']}",
                      "shorten_stop": f"- {o['nights']} {'nacht' if o['nights'] == 1 else 'nachten'} minder in {o['stop']}",
                      "remove_stop": f"- {o['stop']} valt uit de route"}[o["op"]])
    lines += ["", f"De reis duurt nu {ctx['days_after']} dagen: " + ", ".join(f"{r['stop']} ({r['nights']})" for r in ctx["route_after"]) + "."]
    before, after = int(ctx["price_before"]), int(ctx["price_after"])
    fmt = lambda x: f"{x:,}".replace(",", ".")
    lines.append(f"De nieuwe indicatieprijs is {fmt(after)} euro voor het hele gezin (was {fmt(before)} euro).")
    if ctx["manual"]:
        lines.append("Op " + " en ".join(o["note"] or o["op"].replace("_", " ") for o in ctx["manual"]) + " kom ik nog bij je terug.")
    lines += ["We checken de beschikbaarheid nog bij onze partners.", "", "Hartelijke groet,", ctx["specialist"]]
    if not ctx["applied"]:
        lines[2] = "Dank voor je bericht. Ik kijk er persoonlijk naar."
    return {"subject": f"Aangepast voorstel {ctx['trip']['destination']}", "body": "\n".join(lines)}


def partner_reply(ctx: dict) -> dict:
    t = (ctx["mail"]["body"] + "\n" + "\n".join(a["text"] for a in ctx["mail"].get("attachments", []))).lower()
    no = re.search(r"fully booked|unfortunately|not available|volgeboekt|helaas|available: no", t)
    yes = re.search(r"confirm|available: yes|available\b|bevestig|beschikbaar|our offer|please find", t)
    price = re.search(r"eur\s?([\d.,]+)|€\s?([\d.,]+)", t)
    from .money import parse_amount
    eur = parse_amount(price.group(1) or price.group(2)) if price else None
    return {"available": False if no else (True if yes else None), "price_eur": eur,
            "note": ctx["mail"]["body"].split("\n\n")[1][:120] if "\n\n" in ctx["mail"]["body"] else "",
            "needs_person": bool(re.search(r"\?|can offer|instead|alternative", t))}


def trip_alert(ctx: dict) -> dict:
    f, st = ctx["flight"], ctx["status"]
    first = first_name(ctx["family"]["name"])
    what = "is geannuleerd" if st["status"] == "cancelled" else f"heeft ongeveer {st['delay_minutes']} minuten vertraging"
    body = (f"Beste {first},\n\nJullie vlucht {f['number']} op {f['date']} {what}. We kijken nu naar de mogelijkheden "
            f"en laten zo snel mogelijk weten wat dat voor de transfer en het eerste hotel betekent.\n\n"
            f"Is het dringend? Bel dan onze 24/7 lijn: {ctx['emergency_line']}.\n\nHartelijke groet,\n{ctx['specialist']}")
    return {"subject": f"Jullie vlucht {f['number']}", "body": body}


def _first(ctx):
    return (ctx.get("family") or {}).get("name", "").split(" ")[0] or "allemaal"


def _eur(x):
    return f"{round(x):,}".replace(",", ".")


def alternatives(ctx: dict) -> dict:
    lines = [f"Beste {_first(ctx)},", "", f"Naast het voorstel van {_eur(ctx['current']['sell_eur'])} euro heb ik twee andere versies gemaakt:", ""]
    for v in ctx["versions"]:
        lines.append(f"{v['label']}: " + ", ".join(f"{r['stop']} ({r['nights']})" for r in v["route"]) + f". Ongeveer {_eur(v['sell_eur'])} euro voor het hele gezin.")
    lines += ["", "Laat weten welke jullie het meest aanspreekt, dan werk ik die verder uit.", "", "Hartelijke groet,", ctx["specialist"]]
    return {"subject": f"Twee andere versies voor {ctx['trip']['destination']}", "body": "\n".join(lines)}


def complaint_reply(ctx: dict) -> dict:
    t = ctx["mail"]["body"].lower()
    topics = [k for k, ws in {"hotel": ["hotel", "kamer", "room", "pool", "zwembad"], "transfer": ["transfer", "pick-up", "ophalen"],
                              "guide": ["gids", "guide"], "flight": ["vlucht", "flight"], "communication": ["niemand neemt op", "no answer"]}.items()
              if any(w in t for w in ws)] or ["other"]
    now = bool(re.search(r"\b(nu|now|staan|we zijn hier|right now|vandaag)\b", t))
    high = now or "!!" in ctx["mail"]["body"] or "veilig" in t
    sev = "high" if high else ("low" if re.search(r"prima|fine|maar ik wil wel even kwijt", t) else "medium")
    first = _first(ctx)
    lines = [f"Beste {first},", "", "Wat vervelend dat dit gebeurt, en dank dat je het meteen laat weten."]
    if ctx.get("trip") and now:
        lines.append(f"We gaan er nu direct mee aan de slag. Bel bij spoed onze 24/7 lijn: {ctx['emergency_line']}.")
    lines += ["Ik zoek uit wat er is misgegaan en laat je vandaag nog weten wat we doen.", "", "Hartelijke groet,", ctx["specialist"]]
    actions = {"hotel": "Hotel bellen en een andere kamer of hotel vragen", "transfer": "Lokale partner bellen over de transfer",
               "guide": "Feedback aan de lokale partner over de gids", "flight": "Vluchtstatus en opties nagaan",
               "communication": "Nagaan waarom de familie ons niet kon bereiken", "other": "Situatie uitzoeken met de specialist"}
    return {"severity": sev, "while_travelling": now, "topics": topics, "actions": [actions[x] for x in topics] + (["Teamleider informeren"] if sev == "high" else []),
            "subject": "Re: " + ctx["mail"]["subject"], "body": "\n".join(lines)}


def next_trip(ctx: dict) -> dict:
    kids = ctx["family"]["child_ages"]
    lines = [f"Beste {_first(ctx)},", "", "Wat leuk dat jullie met ons op reis zijn geweest. Ik dacht al even mee over een volgende keer:", ""]
    for o, k in zip(ctx["suggestions"], ctx["knowledge"] + [""] * 2):
        lines.append(f"{o['name']}: met kinderen van {', '.join(str(a) for a in kids)} past er veel, de beste tijd is {o['best']}.")
    lines += ["", "Geen haast hoor. Als jullie willen, maak ik een eerste idee.", "", "Hartelijke groet,", tenant().short_name]
    return {"subject": "Een idee voor jullie volgende reis", "body": "\n".join(lines)}


def extras(ctx: dict) -> dict:
    lines = [f"Beste {_first(ctx)},", "", "Een paar extra's die goed bij jullie passen:"]
    lines += [f"- {e['name']} in {e['stop']}: {_eur(e['price_eur'])} euro voor het hele gezin" for e in ctx["extras"]]
    if ctx.get("insurance_policy"):
        lines += ["", ctx["insurance_policy"].replace(" (Sandbox voorbeeld.)", "")]
    lines += ["", "Zeg het maar als je iets wilt toevoegen.", "", "Hartelijke groet,", ctx["specialist"]]
    return {"subject": "Extra's voor jullie reis", "body": "\n".join(lines)}


def call_notes(ctx: dict) -> dict:
    n = ctx["notes"]
    low = n.lower()
    parts = [p.strip(" -*") for p in re.split(r"[\n;]+", n) if p.strip(" -*")]
    budget = re.search(r"budget\D{0,12}(\d+)[.,]?(\d{3})?\s*(k|duizend)?", low)
    b = None
    if budget:
        b = float(budget.group(1) + (budget.group(2) or ""))
        if budget.group(3):
            b *= 1000
    days = re.search(r"(\d+)\s*(dagen|days)", low)
    return {"summary": parts[0] if parts else "Gesprek met de familie",
            "wishes": [p for p in parts if re.search(r"willen|graag|wens|liever|like|want", p.lower())],
            "changes": [p for p in parts if re.search(r"wijzig|anders|in plaats|langer|korter|skip|overslaan", p.lower())],
            "open_questions": [p for p in parts if p.endswith("?") or re.search(r"uitzoeken|checken|vragen of|weet niet", p.lower())],
            "next_steps": [p for p in parts if re.search(r"sturen|bellen|terugkoppelen|maken|send|call back|volgende week", p.lower())],
            "budget_eur": b, "days": int(days.group(1)) if days else None}


def invoice_extract(ctx: dict) -> dict:
    t = ctx["mail"]["subject"] + "\n" + ctx["mail"]["body"] + "\n" + "\n".join(a["text"] for a in ctx["mail"].get("attachments", []))
    no = re.search(r"\bINV-[\w-]+", t) or re.search(r"(?:factuur|invoice)\s*(?:nr\.?|nummer|no\.?|number|#)?\s*([\d][\w-]+)", t, re.IGNORECASE)
    ref = re.search(rf"{tenant().ref_re}-R\d{{2,}}", t, re.IGNORECASE)
    amt = re.search(r"(?:EUR|€)\s?([\d.,]+)", t)
    days = re.search(r"within (\d+) days|binnen (\d+) dagen", t, re.IGNORECASE)
    from .money import parse_amount
    amount = parse_amount(amt.group(1)) if amt else None
    return {"invoice_no": (no.group(1) if no.re.groups else no.group(0)) if no else None, "reference": ref.group(0).upper() if ref else None, "amount_eur": amount,
            "due_days": int(days.group(1) or days.group(2)) if days else None}


def roadbook_intro(ctx: dict) -> dict:
    d = ctx["trip"]["destination"]
    stops = [r["stop"] for r in ctx["trip"]["route"]]
    intro = (f"Beste {_first(ctx)}, hier is jullie reisboek voor {d}. Jullie reizen langs {', '.join(stops[:-1])} en eindigen in {stops[-1]}. "
             "Neem dit boekje mee: alles wat je onderweg nodig hebt staat erin.")
    kids = (f"Hoi! Jullie gaan naar {d}. Onderweg zie je {stops[0]} en {stops[-1]}. Leuk om te weten: "
            f"je slaapt op {len(stops)} verschillende plekken, je reist meer dan duizend kilometer, en je leert vast een paar woorden in een nieuwe taal.")
    return {"intro": intro, "kids_page": kids}


HANDLERS = {"partner_reply": partner_reply, "alternatives": alternatives, "complaint_reply": complaint_reply, "next_trip": next_trip,
            "extras": extras, "call_notes": call_notes, "invoice_extract": invoice_extract, "roadbook_intro": roadbook_intro, "trip_alert": trip_alert, "change_plan": change_plan, "change_reply": change_reply, "triage": triage, "proposal": proposal, "followup": followup, "partner_request": partner_request,
            "partner_chase": partner_chase, "gds": gds, "answer": answer}


def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    task = re.search(r"\[task:(\w+)\]", _instructions(info))
    if not task or task.group(1) not in HANDLERS:
        raise RuntimeError("sandbox model: unknown task")
    data = HANDLERS[task.group(1)](_context(messages))
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, data)])


def sandbox_model() -> FunctionModel:
    return FunctionModel(_respond, model_name="sandbox")


_flaky_state: dict[str, int] = {}


def test_model(kind: str) -> FunctionModel:
    """Models that misbehave on purpose: 'broken' always errors, 'garbage' first returns invalid output and then
    a valid one, 'slow' raises a timeout."""
    def fn(messages, info: AgentInfo) -> ModelResponse:
        if kind == "broken":
            raise ConnectionError("model endpoint unreachable")
        if kind == "slow":
            raise TimeoutError("model did not answer in time")
        if kind == "garbage":
            n = _flaky_state.get("garbage", 0)
            _flaky_state["garbage"] = n + 1
            if n % 2 == 0:
                return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"nonsense": True})])
        return _respond(messages, info)
    return FunctionModel(fn, model_name=f"test:{kind}")
