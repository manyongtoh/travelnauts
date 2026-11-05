"""Nulmeting: how long work takes today, logged by the pilot group for two weeks before the brain goes live.
The summary gives the minutes per task for the Value page (Team lead > Value > baseline). Per team, never per person."""
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

NAVY, FONT = "1F2A44", "Calibri"
HEAD = PatternFill("solid", fgColor=NAVY)
INPUT = PatternFill("solid", fgColor="FFF6D6")
thin = Side(style="thin", color="D9D9D9")
TASKS = [  # label for the team, key on the Value page
    ("Mail lezen en doorzetten", "triage"), ("Eerste reisvoorstel maken", "proposal"), ("Voorstel aanpassen (wijziging)", "change"),
    ("Opvolgmail (nog niets gehoord)", "followup"), ("Aanvraag aan partner of hotel", "partner_request"),
    ("Herinnering aan partner", "partner_chase"), ("Extra's aanbieden na boeking", "extras"), ("Reisboek en vouchers maken", "roadbook"),
    ("Vraag van een gezin beantwoorden", "answer"), ("Klacht beantwoorden", "complaint_reply"),
    ("Alternatieven zoeken (hotel vol, te duur)", "alternatives"), ("Factuur controleren", "invoice"),
    ("Idee voor een volgende reis", "next_trip"), ("Reiswaarschuwing aan gezin (vlucht, weer)", "trip_alert"),
]
TEAMS = ["Azië", "Afrika", "Amerika"]
N = 600

wb = Workbook()
u = wb.active
u.title = "Uitleg"
lines = [
    ("Nulmeting: hoe lang duurt het werk nu?", 14, True),
    ("", 11, False),
    ("Waarom", 12, True),
    ("Het brein neemt werk voor. Om te laten zien wat dat oplevert, moeten we weten hoe lang het werk nu duurt.", 11, False),
    ("Deze cijfers komen op de pagina Waarde (teamleider). Zonder nulmeting blijven daar schattingen staan.", 11, False),
    ("", 11, False),
    ("Hoe", 12, True),
    ("1. Twee weken lang, voordat het brein meedraait: schrijf na elke taak een regel op het tabblad Logboek.", 11, False),
    ("2. Kies team en taak uit de lijst en vul de minuten in die je er echt aan besteedde (ook onderbroken tijd optellen).", 11, False),
    ("3. Bij een eerste reisvoorstel: vul ook in wanneer de aanvraag binnenkwam en wanneer het voorstel de deur uit ging.", 11, False),
    ("4. Een paar taken vergeten is niet erg. Liever 20 eerlijke regels dan 100 geschatte.", 11, False),
    ("", 11, False),
    ("Wat er niet in komt", 12, True),
    ("Geen namen van collega's en geen klantgegevens. Alleen team, taak en tijd. Cijfers worden per team getoond, nooit per persoon.", 11, False),
    ("", 11, False),
    ("Daarna", 12, True),
    ("Het tabblad Samenvatting rekent per taak de gemiddelde minuten uit. De teamleider zet die op de pagina Waarde", 11, False),
    ("(Teamleider > Waarde: minuten per stuk, uren tot eerste voorstel, vinkje 'Nulmeting gemeten') en slaat op.", 11, False),
]
for i, (t, size, bold) in enumerate(lines, 1):
    c = u.cell(row=i, column=1, value=t)
    c.font = Font(name=FONT, size=size, bold=bold, color=NAVY if bold else "000000")
u.column_dimensions["A"].width = 120

log = wb.create_sheet("Logboek")
cols = [("Datum", 12), ("Team", 12), ("Taak", 42), ("Minuten", 10), ("Aanvraag binnen (alleen eerste voorstel)", 22),
        ("Voorstel verstuurd (alleen eerste voorstel)", 22), ("Uren tot voorstel", 12), ("Opmerking (geen namen)", 40)]
for j, (h, w) in enumerate(cols, 1):
    c = log.cell(row=1, column=j, value=h)
    c.font, c.fill = Font(name=FONT, bold=True, color="FFFFFF"), HEAD
    c.alignment = Alignment(wrap_text=True, vertical="center")
    log.column_dimensions[c.column_letter].width = w
log.row_dimensions[1].height = 34
for r in range(2, N + 2):
    for j in (1, 2, 3, 4, 5, 6, 8):
        c = log.cell(row=r, column=j)
        c.fill, c.border = INPUT, Border(bottom=thin)
    log.cell(row=r, column=1).number_format = "dd-mm-yyyy"
    log.cell(row=r, column=5).number_format = "dd-mm-yyyy hh:mm"
    log.cell(row=r, column=6).number_format = "dd-mm-yyyy hh:mm"
    g = log.cell(row=r, column=7, value=f'=IF(AND(E{r}<>"",F{r}<>""),ROUND((F{r}-E{r})*24,1),"")')
    g.number_format = "0.0"
dv_team = DataValidation(type="list", formula1='"' + ",".join(TEAMS) + '"', allow_blank=True)
dv_task = DataValidation(type="list", formula1=f"=Samenvatting!$A$5:$A${4 + len(TASKS)}", allow_blank=True)
dv_min = DataValidation(type="decimal", operator="between", formula1="0", formula2="600", allow_blank=True,
                        error="Minuten tussen 0 en 600", showErrorMessage=True)
for dv, col in ((dv_team, "B"), (dv_task, "C"), (dv_min, "D")):
    log.add_data_validation(dv)
    dv.add(f"{col}2:{col}{N + 1}")
log.freeze_panes = "A2"
log.conditional_formatting.add(f"F2:F{N + 1}", FormulaRule(formula=[f'AND(F2<>"",E2<>"",F2<E2)'], font=Font(color="B4441F", bold=True)))

s = wb.create_sheet("Samenvatting")
s["A1"] = "Samenvatting: gemiddelde minuten per taak"
s["A1"].font = Font(name=FONT, size=14, bold=True, color=NAVY)
s["A2"] = "Vult zichzelf uit het Logboek. Zet de minuten op de pagina Waarde (Teamleider > Waarde) bij de taak in kolom B."
s["A2"].font = Font(name=FONT, size=9, italic=True)
heads = ["Taak", "Naam op de pagina Waarde", "Aantal keer", "Gemiddeld minuten", "Azië", "Afrika", "Amerika"]
for j, h in enumerate(heads, 1):
    c = s.cell(row=4, column=j, value=h)
    c.font, c.fill = Font(name=FONT, bold=True, color="FFFFFF"), HEAD
L = f"Logboek!$C$2:$C${N + 1}"
M = f"Logboek!$D$2:$D${N + 1}"
T = f"Logboek!$B$2:$B${N + 1}"
for i, (label, key) in enumerate(TASKS, 5):
    s.cell(row=i, column=1, value=label)
    s.cell(row=i, column=2, value=key).font = Font(name="Consolas", size=10, color="666666")
    s.cell(row=i, column=3, value=f"=COUNTIF({L},A{i})")
    s.cell(row=i, column=4, value=f'=IFERROR(ROUND(AVERAGEIF({L},A{i},{M}),0),"")')
    for j, team in enumerate(TEAMS, 5):
        s.cell(row=i, column=j, value=f'=IFERROR(ROUND(AVERAGEIFS({M},{L},A{i},{T},"{team}"),0),"")')
r = 5 + len(TASKS) + 1
s.cell(row=r, column=1, value="Uren van aanvraag tot eerste voorstel (gemiddeld)").font = Font(name=FONT, bold=True)
s.cell(row=r, column=2, value="hours_to_first_proposal").font = Font(name="Consolas", size=10, color="666666")
s.cell(row=r, column=3, value=f'=COUNT(Logboek!$G$2:$G${N + 1})')
s.cell(row=r, column=4, value=f'=IFERROR(ROUND(AVERAGE(Logboek!$G$2:$G${N + 1}),0),"")')
s.cell(row=r + 2, column=1, value="Minder dan 5 keer gemeten? Laat de schatting op de pagina Waarde staan of meet langer.").font = Font(name=FONT, size=9, italic=True)
s.conditional_formatting.add(f"C5:C{4 + len(TASKS)}", FormulaRule(formula=["AND(C5>0,C5<5)"], font=Font(color="B4441F", bold=True)))
s.column_dimensions["A"].width = 46
s.column_dimensions["B"].width = 26
for c in "CDEFG":
    s.column_dimensions[c].width = 14
wb.active = 1
wb.save("build/Nulmeting Travelnauts.xlsx")
