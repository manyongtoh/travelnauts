"""The calculation helper on a small invented rate sheet in the supplier's layout.

Prices per night by season and weekday, the European contracts only, a promotion picked and flagged, children's
beds, mandatory supplements, minimum nights, and an Excel whose formulas arrive at the same totals."""
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from brain.calc import excel, trip
from brain.calc.calculate import Flight, Item, Party, Settings, Stop, calculate
from brain.calc.rates import RateSheet, market_ok

ROOM = "Family Room, Bed and Breakfast\nMax pax:\n- 3 Adults\n- 2 Adults 2 Children\nTHB"
SMALL = "Garden Room, Bed and Breakfast\nMax pax:\n- 2 Adults\nTHB"
WINTER, SUMMER = "01.11.2026 - 31.03.2027", "01.04.2027 - 31.10.2027"


def _hotel(ws, name, contract, rows):
    ws.append([f"{name}\n4 star", contract, "Room details", None, None, "Min ng", "Min pax", "Period", "Days", "Price"])
    for r in rows:
        ws.append(r)


@pytest.fixture
def sheet(tmp_path) -> RateSheet:
    wb = Workbook()
    info = wb.active
    info.title = "Info"
    info.append(["Date created", "16.9.2026."])
    info.append(["Currency", "THB"])
    ws = wb.create_sheet("Bangkok")
    ws.append(["Hotel name", "Contract name"])
    _hotel(ws, "Testhuis Riverside", "Worldwide (Ex. TH)", [
        [None, None, ROOM, None, None, 1, "DBL", SUMMER, "Su, Mo, Tu, We, Th", "3,000.00"],
        [None, None, None, None, None, None, None, SUMMER, "Fr, Sa", "3,500.00"],
        [None, None, None, None, None, None, None, WINTER, "All days of the week", "2,000.00"],
        [None, None, None, None, None, 1, "TPL", SUMMER, "All days of the week", "4,200.00"],
        [None, None, SMALL, None, None, 1, "DBL", SUMMER, "All days of the week", "0.00"],
        [None, None, "Extra bed", None, None, "Min ng", "Min pax", "Period", "Days", "Price"],
        [None, None, "Child Sharing Bed\nPrice\nApplicable for: ALL\nTHB", None, None, 1, "1ADL", "01.11.2026 - 31.10.2027", "All days of the week", "0.00"],
        [None, None, "Extra bed | Child\nPrice\nApplicable for: Family Room\nTHB", None, None, 1, "1ADL", "01.11.2026 - 31.10.2027", "All days of the week", "500.00"],
        [None, None, "Mandatory services", None, None, "Min ng", "Min pax", "Period", "Days", "Price"],
        [None, None, "Gala Dinner | Adult\nPrice\nPer person\nApplicable for: ALL\nTHB", None, None, 1, "1ADL", "31.12.2026 - 31.12.2026", "All days of the week", "1,000.00"],
        [None, None, "Cancellation policy", None, "Days before travel", "Cancellation policy Rule"],
    ])
    ws.append([None, "Special Promotion I Worldwide", "Room details", None, None, "Min ng", "Min pax", "Period", "Days", "Price"])
    ws.append([None, None, ROOM, None, None, 3, "DBL", "01.06.2027 - 30.06.2027", "All days of the week", "2,500.00"])
    ws.append([None, "India & Middle East", "Room details", None, None, "Min ng", "Min pax", "Period", "Days", "Price"])
    ws.append([None, None, ROOM, None, None, 1, "DBL", SUMMER, "All days of the week", "100.00"])
    path = tmp_path / "rates.xlsx"
    wb.save(path)
    return RateSheet(path)


def test_reads_rooms_contracts_and_services(sheet):
    assert sheet.currency == "THB" and sheet.created == date(2026, 9, 16)
    contracts = sheet.contracts("Bangkok", "testhuis")
    assert [h.contract for h in contracts] == ["Worldwide (Ex. TH)", "Special Promotion I Worldwide"]  # India & Middle East left out
    room = contracts[0].rooms[0]
    assert room.name == "Family Room" and room.board == "Bed and Breakfast" and (2, 2) in room.max_pax
    assert len(contracts[0].rooms[1].rates) == 0  # a price of 0 is "on request": nothing to calculate with
    assert {s.label for s in contracts[0].services} >= {"Child Sharing Bed", "Extra bed | Child", "Gala Dinner | Adult"}


def test_market_rule():
    assert market_ok("Worldwide (Ex. TH)") and market_ok("Europe, Americas, Africa")
    assert not market_ok("India & Middle East") and not market_ok("Worldwide (Ex. Europe)")


def test_price_follows_season_weekday_and_children(sheet):
    # Thu 1 and Fri 2 July 2027: weekday then weekend price; two children: one shares free, one extra bed
    c = calculate(sheet, Party(2, [5, 9]), date(2027, 7, 1), [Stop("Bangkok", "Testhuis", 2)], alternatives=0)
    assert [n.price for n in c.nights] == [3000 + 500, 3500 + 500]
    assert "kind deelt bed: Child Sharing Bed" in c.nights[0].notes and "extra bed kind: Extra bed | Child" in c.nights[0].notes
    # in winter the single price for all days applies
    w = calculate(sheet, Party(2, [5]), date(2027, 2, 1), [Stop("Bangkok", "Testhuis", 1)], alternatives=0)
    assert w.nights[0].price == 2000


def test_cheapest_contract_is_a_promotion_and_says_so(sheet):
    c = calculate(sheet, Party(2, []), date(2027, 6, 10), [Stop("Bangkok", "Testhuis", 2)], alternatives=0)
    assert c.nights[0].price == 2500 and c.nights[0].contract.startswith("Special Promotion")
    assert any("promotie" in x for x in c.checks) and any("minimaal 3 nachten, gepland 2" in x for x in c.checks)


def test_mandatory_supplement_per_adult(sheet):
    c = calculate(sheet, Party(2, [5]), date(2026, 12, 31), [Stop("Bangkok", "Testhuis", 1)], alternatives=0)
    assert c.nights[0].price == 2000 + 2 * 1000
    assert "verplicht: Gala Dinner | Adult" in c.nights[0].notes


def test_older_children_count_as_adults(sheet):
    c = calculate(sheet, Party(2, [13]), date(2027, 7, 5), [Stop("Bangkok", "Testhuis", 1)], alternatives=0,
                  settings=Settings(child_max_age=11))
    assert c.party.split(11) == (3, 0)
    assert "(3 volw.)" in c.nights[0].rooms and c.nights[0].price == 4200  # the TPL price, no child bed
    # in winter the hotel has only a DBL price: three adults cannot be priced, and that is a check, not a guess
    w = calculate(sheet, Party(2, [13]), date(2027, 2, 1), [Stop("Bangkok", "Testhuis", 1)], alternatives=0)
    assert w.nights[0].price == 0 and any("geen kamer met een prijs" in x for x in w.checks)


def test_unknown_hotel_is_a_check_not_a_crash(sheet):
    c = calculate(sheet, Party(2, []), date(2027, 2, 1), [Stop("Bangkok", "Nergenshuis", 2)], alternatives=0)
    assert all(n.price == 0 for n in c.nights) and any("Nergenshuis" in x for x in c.checks)


def test_euro_margin_and_suggested_prices(sheet):
    c = calculate(sheet, Party(2, [5, 9]), date(2027, 2, 1), [Stop("Bangkok", "Testhuis", 3)],
                  items=[Item("Luchthaven - hotel", date(2027, 2, 1), 1000, 500),
                         Item("Olifanten", date(2027, 2, 2), 100, 50, kind="excursion", currency="AUD")],
                  flights=[Flight("AMS-BKK", 1000, 750)], alternatives=0)
    s = c.settings
    hotels = 3 * (2000 + 500)
    expected = hotels * s.rate_to_eur + (2 * 1000 + 2 * 500) * s.rate_to_eur + (2 * 100 + 2 * 50) * s.other_rates["AUD"] + 2 * 1000 + 2 * 750
    assert c.purchase_eur == pytest.approx(expected)
    pa, pc = c.price_per_person()
    assert (2 * pa + 2 * pc) * (1 - s.target_margin) == pytest.approx(expected)
    assert pa > pc


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice needed to recalculate the formulas")
def test_excel_formulas_arrive_at_the_same_totals(sheet, tmp_path):
    c = calculate(sheet, Party(2, [5, 9]), date(2027, 2, 1), [Stop("Bangkok", "Testhuis", 3)],
                  items=[Item("Luchthaven - hotel", date(2027, 2, 1), 1000, 500)], flights=[Flight("AMS-BKK", 1000, 750)],
                  alternatives=0)
    out = tmp_path / "calc.xlsx"
    excel.write(c, str(out), "Test")
    subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(tmp_path / "re"), str(out)],
                   check=True, capture_output=True, timeout=120)
    ws = load_workbook(tmp_path / "re" / "calc.xlsx", data_only=True)["CALC"]
    values = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=4).value for r in range(13, 40)}
    assert values["Totaal inkoop"] == pytest.approx(c.purchase_eur, abs=0.01)
    assert values["Marge"] == pytest.approx(c.settings.target_margin, abs=0.001)  # suggested prices are rounded to euros
    errors = [cell.coordinate for row in ws.iter_rows() for cell in row if isinstance(cell.value, str) and cell.value.startswith("#")]
    assert not errors
    wb = load_workbook(out)
    assert {"CALC", "Alternatieven", "Controleren"} <= set(wb.sheetnames)


def test_trip_file_and_command(sheet, tmp_path):
    t = {"title": "Test", "party": {"adults": 2, "children": [6]}, "start": "2027-02-01",
         "stops": [{"city": "Bangkok", "hotel": "Testhuis", "nights": 2}],
         "items": [{"label": "Transfer", "adult": 800, "child": 400}], "settings": {"target_margin": 0.2}}
    path = tmp_path / "trip.json"
    path.write_text(json.dumps(t))
    loaded = trip.load(path)
    assert loaded["settings"].target_margin == 0.2 and loaded["party"].children == [6]
    r = subprocess.run([sys.executable, "-m", "brain.cli", "calc", str(path), "--rates", str(sheet.path)],
                       capture_output=True, text=True, timeout=120, cwd=Path(__file__).parents[1], check=False)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "trip.xlsx").exists() and "inkoop EUR" in r.stdout
