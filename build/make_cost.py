"""Gemma on Azure: what it costs a month. Every grey cell is an assumption to replace with Travelnauts' own numbers
and the Azure price list on the day; the totals recalculate."""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

NAVY, FONT = "1F2A44", "Calibri"
ASSUME = PatternFill("solid", fgColor="EDEDED")
wb = Workbook()
ws = wb.active
ws.title = "Cost per month"
ws["A1"] = "Gemma 4 on Azure: cost per month (estimate)"
ws["A1"].font = Font(name=FONT, size=14, bold=True, color=NAVY)
ws["A2"] = "Grey cells are assumptions. Prices are pay-as-you-go list prices in USD found on 5 Nov 2026; check them in the Azure pricing calculator."
ws["A2"].font = Font(name=FONT, size=9, italic=True)

rows = [
    ("Volume", None, None),
    ("Mails a day (families and partners)", 40, "sandbox: 25 family mails plus partner replies"),
    ("Proposals and new versions a day", 8, ""),
    ("Other drafts a day (follow-ups, answers, partner mails, extras)", 30, ""),
    ("Working days a month", 22, ""),
    ("Office hours a day the model stays warm", 10, "08:00 to 18:00; outside it scales to zero"),
    ("Speed on the GPU", None, None),
    ("Seconds per mail, small model (e4b) on a T4", 4, "estimate; measure in the Azure test"),
    ("Seconds per proposal, small model on a T4", 25, "estimate"),
    ("Seconds per mail, 26B or 31B on an A100", 6, "estimate; 31B hosted free tier took 37 s on a busy shared service"),
    ("Seconds per proposal, 26B or 31B on an A100", 30, "estimate"),
    ("Cold start minutes a day (model loading after scale to zero)", 15, "a few loads a day"),
    ("Prices (USD per GPU hour)", None, None),
    ("Serverless GPU T4 (Container Apps, per second)", 0.32, "third-party guidance; Microsoft's page shows it only in the calculator"),
    ("Serverless GPU A100 (Container Apps, per second)", 2.34, "third-party guidance"),
    ("VM T4 always on (NC4as T4 v3, West Europe)", 0.658, "azurespeed / devzero list price"),
    ("VM A100 always on (NC24ads A100 v4)", 3.673, "azurespeed list price"),
    ("Hours in a month", 730, ""),
]
r = 4
cell = {}
for label, val, note in rows:
    ws.cell(row=r, column=1, value=label)
    if val is None:
        ws.cell(row=r, column=1).font = Font(name=FONT, bold=True, color=NAVY)
    else:
        c = ws.cell(row=r, column=2, value=val)
        c.fill = ASSUME
        ws.cell(row=r, column=3, value=note).font = Font(name=FONT, size=9, color="666666")
        cell[label] = f"B{r}"
    r += 1
C = cell
busy_small = f"(({C['Mails a day (families and partners)']}+{C['Other drafts a day (follow-ups, answers, partner mails, extras)']})*{C['Seconds per mail, small model (e4b) on a T4']}+{C['Proposals and new versions a day']}*{C['Seconds per proposal, small model on a T4']})/3600+{C['Cold start minutes a day (model loading after scale to zero)']}/60"
busy_big = f"(({C['Mails a day (families and partners)']}+{C['Other drafts a day (follow-ups, answers, partner mails, extras)']})*{C['Seconds per mail, 26B or 31B on an A100']}+{C['Proposals and new versions a day']}*{C['Seconds per proposal, 26B or 31B on an A100']})/3600+{C['Cold start minutes a day (model loading after scale to zero)']}/60"
days, warm = C["Working days a month"], C["Office hours a day the model stays warm"]
r += 1
ws.cell(row=r, column=1, value="Options").font = Font(name=FONT, bold=True, color=NAVY)
ws.cell(row=r, column=2, value="USD a month").font = Font(name=FONT, bold=True, color=NAVY)
ws.cell(row=r, column=3, value="What you get").font = Font(name=FONT, bold=True, color=NAVY)
opts = [
    ("1. Small model, serverless T4, only when used", f"={busy_small}*{days}*{C['Serverless GPU T4 (Container Apps, per second)']}",
     "Cheapest. First mail after a quiet spell waits for the model to load (about a minute)."),
    ("2. Small model, serverless T4, warm in office hours", f"={warm}*{days}*{C['Serverless GPU T4 (Container Apps, per second)']}",
     "Answers at once during the day; nights and weekends scale to zero."),
    ("3. 26B or 31B, serverless A100, only when used", f"={busy_big}*{days}*{C['Serverless GPU A100 (Container Apps, per second)']}",
     "The quality of the hosted 31B run, paying only for busy seconds."),
    ("4. 26B or 31B, serverless A100, warm in office hours", f"={warm}*{days}*{C['Serverless GPU A100 (Container Apps, per second)']}",
     "Best quality, answers at once in the day."),
    ("5. Small model, T4 VM always on", f"={C['Hours in a month']}*{C['VM T4 always on (NC4as T4 v3, West Europe)']}", "Simple, but pays for every idle night."),
    ("6. 26B or 31B, A100 VM always on", f"={C['Hours in a month']}*{C['VM A100 always on (NC24ads A100 v4)']}", "Only worth it at much higher volume."),
]
for label, f, what in opts:
    r += 1
    ws.cell(row=r, column=1, value=label)
    c = ws.cell(row=r, column=2, value=f)
    c.number_format = '"$"#,##0'
    ws.cell(row=r, column=3, value=what)
r += 2
ws.cell(row=r, column=1, value="GPU busy hours a day: small model").font = Font(name=FONT, size=9)
ws.cell(row=r, column=2, value=f"={busy_small}").number_format = "0.00"
ws.cell(row=r + 1, column=1, value="GPU busy hours a day: 26B or 31B").font = Font(name=FONT, size=9)
ws.cell(row=r + 1, column=2, value=f"={busy_big}").number_format = "0.00"
r += 3
ws.cell(row=r, column=1, value="Not included: the app itself (Container Apps, Postgres, storage, monitoring), which the infra plan sizes separately; quota requests for GPUs; staff time.").font = Font(name=FONT, size=9, italic=True)
ws.column_dimensions["A"].width = 62
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 80
for row in ws.iter_rows():
    for c in row:
        if c.font.name != FONT:
            c.font = Font(name=FONT, size=c.font.size or 11, bold=c.font.bold, italic=c.font.italic, color=c.font.color)
        c.alignment = Alignment(vertical="top", wrap_text=c.column == 3)
wb.save("build/Gemma on Azure cost.xlsx")
