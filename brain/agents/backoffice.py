"""Back office agents from the agents slide:

  invoices        reads a supplier invoice, finds the booking and the offer we accepted, and says whether the
                  amount matches, differs or cannot be placed. Payment stays a person's decision.
  roadbook        builds the roadbook (day by day, hotels, activities, emergency numbers, a page for the
                  children) and one voucher per partner, as PDF drafts. A specialist checks before release.
  booking_check   checks every booked trip's file: partners confirmed, approved offer, flights, payment,
                  insurance, passports, roadbook. Lists what is missing.
"""
from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import today as clock_today
from ..clock import utcnow
from ..db import Draft, InvoiceCheck, Mail, PartnerRequest, Setting, TripRequest
from ..files import files_dir
from ..identity import agent
from ..synth.world import DESTINATIONS
from ..tenant import tenant
from ..toolserver import server
from .change import latest_version
from .common import audit, run_step

# Invoices ------------------------------------------------------------------------------------

class InvoiceFields(BaseModel):
    invoice_no: str | None = None
    reference: str | None = Field(None, description="our booking reference, like WW-R012")
    amount_eur: float | None = None
    due_days: int | None = None


def invoices(s: Session, mail_id: str) -> InvoiceCheck:
    me = agent("invoice_matcher")
    m = s.get(Mail, mail_id)
    existing = s.scalars(select(InvoiceCheck).where(InvoiceCheck.mail_id == mail_id)).first()
    if existing:  # safe to repeat
        return existing
    with audit(s, "invoice_matcher", mail_id, m.subject) as box:
        info = server.call(s, me, "partners.read_reply", mail_id=mail_id)
        f, _ = run_step(s, "invoice_extract", InvoiceFields, "Read the supplier invoice in CONTEXT.mail (and its attachments) and "
                        "return the invoice number, our booking reference, the total amount in euro and the payment term in days.",
                        {"mail": info["mail"]})
        pr = None
        rows = []
        if f.reference:
            rows = s.scalars(select(PartnerRequest).where(
                PartnerRequest.request_id == f.reference.upper().replace(f"{tenant().reference_prefix}-", "").lower())).all()
            mine = [r for r in rows if r.partner_id == m.partner_id] if m.partner_id else rows
            pr = mine[0] if len(mine) == 1 else None  # several partners on the trip and no sender match: a person picks
        expected = (pr.offer or {}).get("price_eur") if pr and pr.status == "answered" else None
        from ..money import amounts as _amounts_in
        in_text = _amounts_in(info["mail"]["subject"] + "\n" + info["mail"]["body"] + "\n" +
                              "\n".join(a["text"] for a in info["mail"].get("attachments", [])))
        misread = f.amount_eur is not None and in_text and all(abs(f.amount_eur - a) > 1 for a in in_text)
        if f.invoice_no:
            dup = s.scalars(select(InvoiceCheck).where(InvoiceCheck.invoice_no == f.invoice_no,
                                                       InvoiceCheck.partner_id == m.partner_id)).first()
        else:  # no number read: same partner, same trip and same amount counts as a likely duplicate
            dup = s.scalars(select(InvoiceCheck).where(InvoiceCheck.partner_id == m.partner_id, InvoiceCheck.partner_id.is_not(None),
                                                       InvoiceCheck.request_id == (pr.request_id if pr else None),
                                                       InvoiceCheck.amount_eur == f.amount_eur)).first() if pr else None
        trip = s.get(TripRequest, pr.request_id) if pr else None
        if misread:
            status, note = "check", f"Bedrag gelezen als {f.amount_eur} euro, maar de factuur noemt {', '.join(f'{a:g}' for a in in_text)}: controleer"
        elif dup is not None:
            status, note = "duplicate", f"Zelfde factuurnummer {f.invoice_no} al ontvangen op {dup.created_at:%d-%m}: niet nog eens betalen"
        elif trip is not None and trip.status != "booked":
            status, note = "check", f"Reis {trip.id.upper()} is niet geboekt (status {trip.status.replace('_', ' ')}): eerst navragen"
        elif pr is None and rows and not m.partner_id:
            status, note = "unknown", "Afzender onbekend en meerdere partners op deze reis: kies de partner"
        elif pr is None or expected is None or f.amount_eur is None:
            status, note = "unknown", "Geen geaccepteerde offerte gevonden bij deze referentie"
        elif abs(f.amount_eur - expected) <= 1:
            status, note = "match", "Bedrag klopt met de geaccepteerde offerte"
        else:
            status, note = "differs", f"Factuur {f.amount_eur:,.0f} euro, afgesproken {expected:,.0f} euro (verschil {f.amount_eur - expected:+,.0f} euro)".replace(",", ".")
        chk = InvoiceCheck(mail_id=mail_id, partner_id=m.partner_id, request_id=pr.request_id if pr else None, invoice_no=f.invoice_no,
                           amount_eur=f.amount_eur, expected_eur=expected, status=status, note=note)
        s.add(chk)
        m.status = "done"
        s.commit()
        box["output"] = f"{status} {f.invoice_no or ''}"
    return chk


# Roadbook and vouchers ---------------------------------------------------------------------------

class RoadbookText(BaseModel):
    intro: str = Field(description="two or three warm sentences in Dutch for the family")
    kids_page: str = Field(description="a short page in Dutch for the children: what they will see, three fun facts")


def _pdf(path, title: str, blocks: list[tuple[str, str]]) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    ss = getSampleStyleSheet()
    ink = colors.HexColor("#1F2F45")
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=ink, fontName="Helvetica-Bold", fontSize=22, leading=26, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor("#A4441D"), fontName="Helvetica-Bold", fontSize=13)
    body = ParagraphStyle("b", parent=ss["BodyText"], textColor=ink, fontSize=10.5, leading=15)
    story = [Paragraph(title, h1), Spacer(1, 6 * mm)]
    for head, text in blocks:
        if head == "PAGEBREAK":
            story.append(PageBreak())
            continue
        if head:
            story.append(Paragraph(head, h2))
        for para in text.split("\n"):
            story.append(Paragraph(para.replace("&", "&amp;").replace("<", "&lt;"), body))
        story.append(Spacer(1, 4 * mm))
    path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
                      title=title, author=tenant().name).build(story)
    return str(path)


def roadbook(s: Session, request_id: str) -> Draft:
    me = agent("roadbook")
    tr = server.call(s, me, "ts.read_trip", request_id=request_id)
    fam = server.call(s, me, "ts.read_relation", family_id=tr["family_id"])
    base = latest_version(s, request_id)
    if base is None:
        raise ValueError("No approved offer to build a roadbook from")
    d = DESTINATIONS[tr["destination"]]
    with audit(s, "roadbook", request_id) as box:
        tips = server.call(s, me, "knowledge.search", query=f"beste reistijd {d['nl']}", destination=tr["destination"], k=1)
        txt, _ = run_step(s, "roadbook_intro", RoadbookText, "Write the intro and the children's page for the roadbook of "
                          "CONTEXT.family to CONTEXT.trip. Use only facts from CONTEXT.", {
                              "family": {"name": fam["contact_name"], "child_ages": fam["child_ages"]},
                              "trip": {"destination": d["nl"], "route": base.data["route"]},
                              "knowledge": [t["body"] for t in tips]})
        start = date.fromisoformat(tr["depart_date"]) if tr.get("depart_date") else None
        days, day = [], 1
        for r in base.data["route"]:
            when = f" (vanaf {(start + timedelta(days=day)).strftime('%d-%m')})" if start else ""
            days.append((f"Dag {day}: {r['stop']}{when}",
                         f"{r['nights']} {'nacht' if r['nights'] == 1 else 'nachten'} in {r['hotel']}.\n"
                         + ("Wat jullie gaan doen: " + ", ".join(r.get("activities", [])) if r.get("activities") else "")))
            day += r["nights"]
        from .trip_monitor import flight_fields
        fl = [flight_fields(f) for f in tr.get("flights", [])]
        flights = "\n".join(f"{f['number'] or '?'} op {f['date'] or '?'}: {f['from']} naar {f['to']}" for f in fl) or "Volgt nog"
        rb_path = files_dir() / "roadbooks" / f"roadbook_{request_id}.pdf"
        _pdf(rb_path, f"Reisboek {d['nl']}, familie {fam['surname']}",
             [("", txt.intro), ("Vluchten", flights), *days,
              ("Belangrijke nummers", f"{tenant().short_name} 24/7: {tenant().emergency_line}\nJullie specialist: via de app of mail"),
              ("PAGEBREAK", ""), (f"Voor de kinderen ({', '.join(str(a) for a in fam['child_ages'])} jaar)", txt.kids_page)])
        vouchers = []
        partners = {p["id"]: p for p in server.call(s, me, "partners.list", destination=tr["destination"])}
        for r in base.data["route"]:
            p = next((x for x in partners.values() if x["name"] == r["hotel"]), None)
            if not p:
                continue
            vp = files_dir() / "vouchers" / f"voucher_{request_id}_{p['id']}.pdf"
            _pdf(vp, f"Voucher {p['name']}", [("", f"Referentie {tenant().reference(request_id)}\nGasten: familie {fam['surname']}, "
                                                   f"{fam['adults']} volwassenen en {len(fam['child_ages'])} kinderen\n"
                                                   f"Verblijf: {r['nights']} nachten in {r['stop']}\nBetaald door {tenant().name}. "
                                                   f"Extra's ter plaatse zelf afrekenen.")])
            vouchers.append({"partner": p["name"], "path": str(vp)})
        dr = Draft(kind="roadbook", request_id=request_id, title=f"Reisboek en {len(vouchers)} vouchers", body=txt.intro + "\n\n" + txt.kids_page,
                   data={"roadbook": str(rb_path), "vouchers": vouchers,
                         "warnings": ["Controleer namen, data en tijden voordat je het reisboek vrijgeeft"]})
        s.add(dr)
        s.commit()
        box["output"] = f"roadbook + {len(vouchers)} vouchers"
    return dr


# Booking file checks -------------------------------------------------------------------------

def booking_check(s: Session) -> dict:
    me = agent("booking_check")
    with audit(s, "booking_check", "daily") as box:
        files = []
        for t in server.call(s, me, "ts.list_trips", status="booked"):
            dd = date.fromisoformat(t["depart_date"]) if t["depart_date"] else None
            if dd and dd + timedelta(days=t.get("days") or 0) < clock_today():
                continue  # already travelled and home again: nothing left to prepare
            from .partner_desk import current_requests
            prs = current_requests(s, t["id"])
            missing = []
            open_prs = [pr for pr in prs if pr.status not in ("answered",)]
            if open_prs:
                missing.append(f"{len(open_prs)} partner(s) not confirmed")
            if any(pr.status == "unclear" for pr in prs):
                missing.append("a partner answer needs reading: decide on the board")
            if any(pr.status == "chased" for pr in prs):
                missing.append("a partner is silent after a reminder: phone them or choose another")
            if any(pr.status == "answered" and (pr.offer or {}).get("available") is False for pr in prs):
                missing.append("a partner is not available: find another")
            if not s.scalars(select(Draft).where(Draft.request_id == t["id"], Draft.kind.in_(["proposal", "change"]),
                                                 Draft.status == "approved")).first():
                missing.append("no approved offer")
            from .trip_monitor import flight_fields
            if not t["flights"]:
                missing.append("no flights in the file")
            elif any(not (ff["number"] and ff["date"]) for ff in map(flight_fields, t["flights"])):
                missing.append("flight number or date missing in the file")
            if t["payment_status"] != "paid":
                dd = date.fromisoformat(t["depart_date"]) if t["depart_date"] else None
                if dd and dd - clock_today() <= timedelta(weeks=6):
                    missing.append("final payment due (less than 6 weeks to departure)")
            if not t["insurance"]:
                missing.append("no proof of travel insurance")
            if not t["passports_checked"]:
                missing.append("passport names not checked against the booking")
            has = lambda kind, t=t: s.scalars(select(Draft).where(Draft.request_id == t["id"], Draft.kind == kind)).first()
            to_go = (dd - clock_today()).days if dd else None
            from ..jobs import enqueue, pending
            # extras only while there is time to add them (more than three weeks out)
            if to_go is not None and to_go > 21 and not has("extras") and not pending(s, "extras", t["id"]):
                enqueue(s, "extras", {"request_id": t["id"]})
            if not has("roadbook"):
                if to_go is not None and 0 <= to_go <= 21 and not open_prs and not pending(s, "roadbook", t["id"]):
                    enqueue(s, "roadbook", {"request_id": t["id"]})  # three weeks out, once partners confirmed
                missing.append("roadbook not made")
            files.append({"request_id": t["id"], "destination": DESTINATIONS[t["destination"]]["name"], "team_id": t["team_id"],
                          "depart_date": t["depart_date"], "missing": missing, "complete": not missing})
        files.sort(key=lambda f: (f["complete"], f["depart_date"] or "9999"))
        from ..workflow import withdraw_stale_drafts
        withdraw_stale_drafts(s)
        s.merge(Setting(key="report:booking_check", value={"at": utcnow().isoformat(timespec="minutes"), "files": files}))
        s.commit()
        box["output"] = f"{sum(not f['complete'] for f in files)} of {len(files)} files incomplete"
    return {"files": len(files), "incomplete": sum(not f["complete"] for f in files)}
