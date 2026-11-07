"""Write a calculation as a workbook in the layout specialists already use for a dossier: the arrangement prices on
top, the margin calculation under it, the hotels per night beside it, then transfers, excursions and flights.

Every total is a formula, so a specialist can change a price, the exchange rate or the number of nights and the
margin follows. Blue numbers are inputs, yellow cells are assumptions to check.
"""
from __future__ import annotations

from datetime import date

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .calculate import Calculation

FONT = "Arial"
BLUE = Font(name=FONT, color="0000FF")
BLACK = Font(name=FONT)
BOLD = Font(name=FONT, bold=True)
HEAD = Font(name=FONT, bold=True, color="FFFFFF")
TITLE = Font(name=FONT, bold=True, size=14)
NOTE = Font(name=FONT, italic=True, color="595959", size=9)
HEAD_FILL = PatternFill("solid", fgColor="1F2F45")
CHECK_FILL = PatternFill("solid", fgColor="FFFF00")
SUB_FILL = PatternFill("solid", fgColor="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
LINE = Border(top=THIN)
EUR = '€ #,##0;-€ #,##0;"-"'
EUR2 = '€ #,##0.00;-€ #,##0.00;"-"'
NUM = '#,##0;-#,##0;"-"'
PCT = '0.0%;-0.0%;"-"'
RATE = "0.0000"
DATE = "ddd d-m-yyyy"


def _head(ws, row: int, col: int, labels: list[str]):
    for i, label in enumerate(labels):
        c = ws.cell(row=row, column=col + i, value=label)
        c.font, c.fill = HEAD, HEAD_FILL
        c.alignment = Alignment(vertical="center")


def write(calc: Calculation, path: str, title: str = "") -> str:
    s = calc.settings
    adults, children = calc.party.split(s.child_max_age)
    wb = Workbook()
    ws = wb.active
    ws.title = "CALC"
    for col, width in {"A": 34, "B": 13, "C": 9, "D": 13, "E": 3, "F": 6, "G": 15, "H": 16, "I": 30, "J": 34,
                       "K": 50, "L": 14, "M": 52}.items():
        ws.column_dimensions[col].width = width

    ws["A1"] = title or f"Calculatie voor {calc.party.describe()}, vertrek {calc.start:%d-%m-%Y}"
    ws["A1"].font = TITLE
    ws["A2"] = (f"Eerste opzet door het brein op {date.today():%d-%m-%Y}. Blauw = invoer, geel = aanname die "
                f"gecontroleerd moet worden. Er is niets geboekt.")
    ws["A2"].font = NOTE

    # --- assumptions (each in its own cell; every formula refers to these)
    _head(ws, 4, 1, ["Instellingen", "Waarde", "", "Bron"])
    ws.merge_cells("D4:D4")
    settings = [("Koers " + calc.currency + " naar EUR", s.rate_to_eur, RATE, s.rate_source),
                *[(f"Koers {k} naar EUR", v, RATE, s.other_rates_source) for k, v in s.other_rates.items()],
                ("Doelmarge", s.target_margin, PCT, s.margin_source),
                ("Kinderen tot en met (jaar)", s.child_max_age, "0", s.child_age_source)]
    ref = {}
    r = 5
    for label, value, fmt, src in settings:
        ws.cell(row=r, column=1, value=label).font = BLACK
        c = ws.cell(row=r, column=2, value=value)
        c.font, c.fill, c.number_format = BLUE, CHECK_FILL, fmt
        ws.cell(row=r, column=4, value=src).font = NOTE
        ref[label] = f"$B${r}"
        r += 1
    rate_ref = {calc.currency: ref["Koers " + calc.currency + " naar EUR"],
                **{k: ref[f"Koers {k} naar EUR"] for k in s.other_rates}}
    margin_ref = ref["Doelmarge"]

    # --- hotels per night (G:M), like the dossier's day table
    top = 4
    _head(ws, top, 7, ["Dag", "Datum", "Plaats", "Hotel", "Kamerindeling", f"{calc.currency} per nacht", "Opmerking"])
    hr = top + 1
    for n in calc.nights:
        ws.cell(row=hr, column=7, value=n.day).font = BLACK
        c = ws.cell(row=hr, column=8, value=n.on)
        c.number_format, c.font = DATE, BLACK
        ws.cell(row=hr, column=9, value=n.city).font = BLACK
        ws.cell(row=hr, column=10, value=n.hotel).font = BLACK
        ws.cell(row=hr, column=11, value=n.rooms).font = BLACK
        c = ws.cell(row=hr, column=12, value=round(n.price, 2))
        c.font, c.number_format = BLUE, NUM
        if n.contract:
            c.comment = Comment(f"Contract: {n.contract}", "brein")
        note = "; ".join(n.notes)
        if not n.price:
            note = "GEEN PRIJS: " + note
            c.fill = CHECK_FILL
        ws.cell(row=hr, column=13, value=note).font = NOTE
        hr += 1
    hotel_first, hotel_last = top + 1, hr - 1
    ws.cell(row=hr, column=11, value=f"Inkoop hotels {calc.currency}").font = BOLD
    c = ws.cell(row=hr, column=12, value=f"=SUM(L{hotel_first}:L{hotel_last})")
    c.font, c.number_format, c.border = BOLD, NUM, LINE
    hotel_total = f"$L${hr}"
    ws.cell(row=hr + 1, column=7, value=f"Laatste dag {calc.nights[-1].day + 1 if calc.nights else 1}: vertrek").font = NOTE

    # --- transfers and excursions (G:M below the hotels)
    ir = hr + 3
    _head(ws, ir, 7, ["Datum", "Soort", "Omschrijving", "Valuta", "Volw. p.p.", "Kind p.p.", "Totaal"])
    ws.cell(row=ir, column=14, value="EUR").font, ws.cell(row=ir, column=14).fill = HEAD, HEAD_FILL
    ws.column_dimensions["N"].width = 13
    ir += 1
    item_first = ir
    for it in calc.items:
        cur = it.currency or calc.currency
        if it.on:
            c = ws.cell(row=ir, column=7, value=it.on)
            c.number_format = DATE
        ws.cell(row=ir, column=8, value=it.kind).font = BLACK
        ws.cell(row=ir, column=9, value=it.label + (" (per groep)" if it.per_group else "")).font = BLACK
        ws.cell(row=ir, column=10, value=cur).font = BLACK
        c = ws.cell(row=ir, column=11, value=it.adult)
        c.font, c.number_format = BLUE, NUM
        c = ws.cell(row=ir, column=12, value=it.child if it.child is not None else it.adult)
        c.font, c.number_format = BLUE, NUM
        if it.per_group:
            ws.cell(row=ir, column=13, value=f"=K{ir}")
        else:
            ws.cell(row=ir, column=13, value=f"=K{ir}*$C$13+L{ir}*$C$14")
        ws.cell(row=ir, column=13).number_format = NUM
        c = ws.cell(row=ir, column=14, value=f"=M{ir}*{rate_ref[cur]}")
        c.number_format = EUR
        ir += 1
    item_last = ir - 1
    has_items = item_last >= item_first

    # --- flights
    fr = ir + 2
    _head(ws, fr, 7, ["Vlucht", "", "Referentie", "", "Volw. p.p. EUR", "Kind p.p. EUR", "Totaal EUR"])
    fr += 1
    flight_first = fr
    for f in calc.flights:
        ws.cell(row=fr, column=7, value=f.label).font = BLACK
        ws.cell(row=fr, column=9, value=f.reference).font = BLACK
        c = ws.cell(row=fr, column=11, value=f.adult_eur)
        c.font, c.number_format = BLUE, EUR2
        c = ws.cell(row=fr, column=12, value=f.child_eur if f.child_eur is not None else f.adult_eur)
        c.font, c.number_format = BLUE, EUR2
        c = ws.cell(row=fr, column=13, value=f"=K{fr}*$C$13+L{fr}*$C$14")
        c.number_format = EUR
        fr += 1
    flight_last = fr - 1
    has_flights = flight_last >= flight_first

    # --- arrangement prices (A12:D17), as in the dossier
    pa, pc = calc.price_per_person()
    _head(ws, 12, 1, ["Arrangement", "Prijs p.p.", "Aantal", "Totaal"])
    ws["A13"], ws["A14"] = "Arrangement volwassenen", "Arrangement kinderen"
    for row, price, count in ((13, round(pa), adults), (14, round(pc), children)):
        ws.cell(row=row, column=1).font = BLACK
        c = ws.cell(row=row, column=2, value=price)
        c.font, c.number_format = BLUE, EUR
        c.comment = Comment("Voorstel van het brein bij de doelmarge. Pas gerust aan: de marge rekent mee.", "brein")
        c = ws.cell(row=row, column=3, value=count)
        c.font = BLUE
        c = ws.cell(row=row, column=4, value=f"=B{row}*C{row}")
        c.number_format = EUR
    ws["A15"] = "Overige bijdragen (bijv. garantiefonds)"
    ws["A15"].font = BLACK
    ws["B15"], ws["C15"] = 0, 1
    ws["B15"].font = ws["C15"].font = BLUE
    ws["B15"].number_format = EUR2
    ws["D15"] = "=B15*C15"
    ws["D15"].number_format = EUR
    ws["A16"], ws["D16"] = "Totaal verkoop", "=SUM(D13:D15)"
    ws["A16"].font = ws["D16"].font = BOLD
    ws["D16"].number_format, ws["D16"].border = EUR, LINE

    # --- margin (A19:D29)
    _head(ws, 19, 1, ["Margeberekening", "Inkoop", "Koers", "EUR"])
    rows = [("Hotels", f"={hotel_total}", rate_ref[calc.currency])]
    for kind, label in (("transfer", "Transfers"), ("excursion", "Excursies en arrangementen")):
        if has_items:
            rows.append((label, None, None, f'=SUMIF($H${item_first}:$H${item_last},"{kind}",$N${item_first}:$N${item_last})'))
    if has_flights:
        rows.append(("Vluchten", None, None, f"=SUM(M{flight_first}:M{flight_last})"))
    mr = 20
    for row in rows:
        ws.cell(row=mr, column=1, value=row[0]).font = BLACK
        if row[1]:
            c = ws.cell(row=mr, column=2, value=row[1])
            c.number_format = NUM
            c = ws.cell(row=mr, column=3, value=f"={row[2]}")
            c.number_format = RATE
            c = ws.cell(row=mr, column=4, value=f"=B{mr}*C{mr}")
        else:
            c = ws.cell(row=mr, column=4, value=row[3])
        c.number_format = EUR
        mr += 1
    ws.cell(row=mr, column=1, value="Totaal inkoop").font = BOLD
    c = ws.cell(row=mr, column=4, value=f"=SUM(D20:D{mr - 1})")
    c.font, c.number_format, c.border = BOLD, EUR, LINE
    buy = mr
    lines = [("Totaal verkoop", "=D16", EUR), ("Verschil", f"=D{buy + 1}-D{buy}", EUR),
             ("Marge", f"=IF(D{buy + 1}=0,0,D{buy + 2}/D{buy + 1})", PCT),
             ("Doelmarge", f"={margin_ref}", PCT),
             ("Verkoop bij doelmarge", f"=IF({margin_ref}>=1,0,D{buy}/(1-{margin_ref}))", EUR)]
    for i, (label, formula, fmt) in enumerate(lines, start=1):
        ws.cell(row=buy + i, column=1, value=label).font = BOLD if label == "Marge" else BLACK
        c = ws.cell(row=buy + i, column=4, value=formula)
        c.number_format = fmt
        if label == "Marge":
            c.font = BOLD

    ws.freeze_panes = "A4"

    # --- alternatives
    alt = wb.create_sheet("Alternatieven")
    _head(alt, 1, 1, ["Plaats", "Hotel", "Sterren", "Kamerindeling", f"{calc.currency} totaal", "Per nacht"])
    for col, width in {"A": 16, "B": 40, "C": 9, "D": 48, "E": 14, "F": 12}.items():
        alt.column_dimensions[col].width = width
    ar = 2
    stay = {}
    for n in calc.nights:
        stay[n.city] = stay.get(n.city, 0) + 1
    for city, options in calc.alternatives.items():
        for a in options:
            alt.cell(row=ar, column=1, value=city)
            alt.cell(row=ar, column=2, value=a.hotel)
            alt.cell(row=ar, column=3, value=a.stars)
            alt.cell(row=ar, column=4, value=a.rooms)
            c = alt.cell(row=ar, column=5, value=round(a.total))
            c.number_format = NUM
            c = alt.cell(row=ar, column=6, value=f"=E{ar}/{max(stay.get(city, 1), 1)}")
            c.number_format = NUM
            ar += 1
    alt.cell(row=ar + 1, column=1, value="De goedkoopste andere hotels uit dezelfde prijzenlijst die het gezin passen.").font = NOTE

    # --- checks
    chk = wb.create_sheet("Controleren")
    _head(chk, 1, 1, ["Gecontroleerd", "Wat het brein niet zeker weet"])
    chk.column_dimensions["A"].width = 14
    chk.column_dimensions["B"].width = 110
    for i, text in enumerate(calc.checks, start=2):
        chk.cell(row=i, column=1, value="").fill = CHECK_FILL
        chk.cell(row=i, column=2, value=text).font = BLACK
    chk.cell(row=len(calc.checks) + 3, column=2,
             value="Zet een x in kolom A als je het gecontroleerd hebt.").font = NOTE

    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.font and cell.font.name != FONT:
                    f = cell.font
                    cell.font = Font(name=FONT, bold=f.bold, italic=f.italic, color=f.color, size=f.size)
        sheet.sheet_view.showGridLines = False
    for col in range(1, 15):
        ws.column_dimensions[get_column_letter(col)].alignment = Alignment(vertical="top")
    wb.save(path)
    return path
