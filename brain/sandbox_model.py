"""The stand-in model for the sandbox.

It plays the part of the language model without any network: it reads the same instructions and
CONTEXT a real model gets and returns the same typed output, built with simple rules and templates.
That lets us test the whole flow, the screens and the measurements before a real model is attached.
It does not show how good the writing will be; for that, run with BRAIN_MODEL=ollama:gemma4.
"""
from __future__ import annotations

import json
import re

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .synth.world import DESTINATIONS, WISHES

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
    if "news@" in m["from"] or "afmelden" in low or "factuur" in low:
        cat = "other"
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
    out: dict = {"category": cat, "destination": dest if cat != "other" else None,
                 "urgent": cat == "complaint" or "snel reageren" in low, "child_ages": [], "wishes": []}
    if cat == "new_request":
        ages = re.search(r"kinderen (?:\(|van |zijn )([\d en]+?)(?: jaar|\)|\.)", low)
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
        "other": "Geen actie nodig",
    }[cat]
    return out


def _kids(ages: list[int]) -> str:
    if not ages:
        return ""
    if len(ages) == 1:
        return f"jullie kind van {ages[0]}"
    return "de kinderen van " + ", ".join(str(a) for a in ages[:-1]) + f" en {ages[-1]}"


def proposal(ctx: dict) -> dict:
    fam, trip, route, price = ctx["family"], ctx["trip"], ctx["route"], ctx["price"]
    first = fam["name"].split()[0]
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
    lines.append(f"De reis kost ongeveer {eur} euro voor het hele gezin, inclusief vluchten, "
                 f"hotels, transfers en de genoemde activiteiten. Dit is een indicatie.")
    if price.get("warnings"):
        lines.append("Een paar dingen checken we nog bij onze partners: " + "; ".join(price["warnings"]) + ".")
    if trip.get("budget_eur") and price["sell_eur"] > trip["budget_eur"] * 1.05:
        lines.append("Het komt iets boven jullie budget uit. Ik denk graag mee over een paar nachten minder of eenvoudigere hotels.")
    lines += ["", "Laat gerust weten wat jullie ervan vinden, dan passen we het samen aan.", "", "Hartelijke groet,",
              ctx["specialist"], "Travelnauts"]
    return {"subject": f"Jullie reis naar {trip['destination']}: een eerste voorstel", "body": "\n".join(lines),
            "used_sources": used}


def followup(ctx: dict) -> dict:
    fam, trip = ctx["family"], ctx["trip"]
    first = fam["name"].split()[0]
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
            f"Kind regards,\nTravelnauts back office")
    return {"subject": f"Availability request {ctx['reference']} ({t['month']})", "body": body}


def partner_chase(ctx: dict) -> dict:
    body = (f"Dear {ctx['partner']['name']} team,\n\nA kind reminder about our request {ctx['reference']}, sent on "
            f"{ctx['sent_at']}. Could you let us know within two working days?\n\nKind regards,\nTravelnauts back office")
    return {"subject": f"Reminder: {ctx['reference']}", "body": body}


def galileo(ctx: dict) -> dict:
    f = ctx["flight"]
    cmds = [{"cmd": f"A{f['out']}{f['from']}{f['to']}", "explain": "Beschikbaarheid heenreis"},
            {"cmd": f"0{f['seats']}{f['class']}1", "explain": f"{f['seats']} stoelen boeken op regel 1 (na controle)"},
            {"cmd": f"A{f['back']}{f['to']}{f['from']}", "explain": "Beschikbaarheid terugreis"},
            {"cmd": f"0{f['seats']}{f['class']}1", "explain": f"{f['seats']} stoelen boeken op regel 1 (na controle)"}]
    for t in f["travellers"]:
        if t["type"] == "child":
            cmds.append({"cmd": f"N.{t['surname']}/{t['first']}CHD*C{t['age']:02d}", "explain": f"Naam kind ({t['age']} jaar)"})
        else:
            cmds.append({"cmd": f"N.{t['surname']}/{t['first']}MR", "explain": "Naam volwassene (titel controleren)"})
    cmds += [{"cmd": "P.AMSB*TRAVELNAUTS", "explain": "Telefoon kantoor"},
             {"cmd": f"T.TAU/{f['ticket_by']}", "explain": "Uiterste ticketdatum"},
             {"cmd": "R.AGENT", "explain": "Ontvangen van"},
             {"cmd": "*R", "explain": "Boeking tonen ter controle"}]
    return {"commands": cmds, "notes": ["Voornamen van partner en kinderen zijn placeholders: aanvullen uit het paspoort"]}


STOP = {"de", "het", "een", "en", "van", "in", "is", "op", "te", "voor", "met", "we", "wij", "jullie", "naar", "kan",
        "kunnen", "kinderen", "kind", "gezin", "jaar", "geschikt", "hoe", "wat", "welke", "zit", "nog", "goed", "voor", "zijn", "er", "met", "uit", "voeten", "makkelijk"}


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


HANDLERS = {"triage": triage, "proposal": proposal, "followup": followup, "partner_request": partner_request,
            "partner_chase": partner_chase, "galileo": galileo, "answer": answer}


def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    task = re.search(r"\[task:(\w+)\]", _instructions(info))
    if not task or task.group(1) not in HANDLERS:
        raise RuntimeError("sandbox model: unknown task")
    data = HANDLERS[task.group(1)](_context(messages))
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, data)])


def sandbox_model() -> FunctionModel:
    return FunctionModel(_respond, model_name="sandbox")
