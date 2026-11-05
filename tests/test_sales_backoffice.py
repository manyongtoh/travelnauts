from brain.clock import utcnow
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from brain import jobs
from brain.agents import backoffice, proposal, sales, triage
from brain.db import Draft, Family, InvoiceCheck, Mail, PartnerRequest, PriceItem, TripRequest
from brain.files import pdf_text
from brain.guardrails import _amounts
from brain.tenant import tenant


def drafted(s):
    triage.triage_inbox(s)
    tr = s.scalars(select(TripRequest).where(TripRequest.mail_id.is_not(None))).first()
    return tr, proposal.write_proposal(s, tr.id)


def test_alternatives_are_quieter_and_cheaper_and_priced(world):
    tr, base = drafted(world)
    d = sales.alternatives(world, tr.id)
    quiet, cheap = d.data["versions"]
    assert len(quiet["route"]) <= min(3, len(base.data["route"]))
    assert sum(r["nights"] for r in quiet["route"]) == sum(r["nights"] for r in base.data["route"])
    assert cheap["price"]["sell_eur"] <= base.data["price"]["sell_eur"]
    allowed = {round(x) for x in [base.data["price"]["sell_eur"], quiet["price"]["sell_eur"], cheap["price"]["sell_eur"]]}
    assert set(_amounts(d.body)) <= allowed


def test_extras_fit_the_children_and_use_the_calculation_margin(world):
    tr, base = drafted(world)
    fam = world.get(Family, tr.family_id)
    d = sales.extras(world, tr.id)
    have = {a for r in base.data["route"] for a in r["activities"]}
    for e in d.data["extras"]:
        item = world.get(PriceItem, e["price_item"])
        assert e["name"] not in have and item.min_child_age <= min(fam.child_ages)
        assert e["price_eur"] == round(item.cost_eur * (fam.adults + len(fam.child_ages)) * 1.25)


def test_complaint_reply_never_promises_money(world):
    triage.triage_inbox(world)
    jobs.work(world, limit=500)
    replies = world.scalars(select(Draft).where(Draft.kind == "complaint_reply")).all()
    assert replies
    for d in replies:
        assert not any(w in d.body.lower() for w in sales.MONEY)


def test_high_priority_complaint_needs_the_team_lead(world):
    from brain.api.app import app
    m = Mail(id="cx1", received_at=utcnow(), sender="x@example.org", subject="!!!",
             body="We staan nu op het vliegveld en de transfer is er niet!! Niemand neemt op.\n\nAnouk", family_id="fam001", truth={})
    world.add(m)
    world.commit()
    d = sales.complaint(world, "cx1")
    assert d.data["severity"] == "high" and d.data["while_travelling"]
    c = TestClient(app)
    owner = world.get(TripRequest, d.request_id).specialist_id if d.request_id else "sanne-de-vries"
    r = c.post(f"/api/drafts/{d.id}/approve", json={}, headers={"X-Brain-User": owner})
    assert r.status_code == 403


def test_next_trip_skips_places_they_have_been(world):
    fam = next(f for f in world.scalars(select(Family)).all() if f.past_destinations)
    d = sales.next_trip(world, fam.id)
    assert d.data["suggestions"] and not {o["destination"] for o in d.data["suggestions"]} & set(fam.past_destinations)
    assert d.data["specialist_id"]


def test_call_notes_update_the_request(world):
    tr, _ = drafted(world)
    d = sales.call_notes(world, tr.id, "Gebeld met vader\n- willen graag meer strand\n- budget ongeveer 15k\n- vragen of kinderzitjes kunnen?")
    row = world.get(TripRequest, tr.id)
    assert row.budget_eur == 15000 and "willen graag meer strand" in row.wishes
    assert "kinderzitjes" in d.body


def test_invoices_match_differ_or_cannot_be_placed(world):
    triage.triage_inbox(world)
    jobs.work(world, limit=500)
    checks = {c.mail_id: c for c in world.scalars(select(InvoiceCheck)).all()}
    inv = [m for m in world.scalars(select(Mail)).all() if m.truth.get("category") == "invoice"]
    assert inv
    for m in inv:
        assert checks[m.id].status == m.truth["expected_status"], m.subject


def test_partner_offers_in_pdf_are_read(world):
    triage.triage_inbox(world)
    jobs.work(world, limit=500)
    pdf_mails = [m for m in world.scalars(select(Mail)).all() if m.attachments]
    assert pdf_mails
    for m in pdf_mails:
        pr = world.get(PartnerRequest, m.truth["partner_request_id"])
        if m.truth["available"]:
            assert pr.status == "answered" and pr.offer["price_eur"] == m.truth["price_eur"]
        else:
            assert pr.status == "declined"


def test_roadbook_and_vouchers_are_pdfs_for_the_family(world):
    tr = next(t for t in world.scalars(select(TripRequest)).all() if t.status == "booked")
    fam = world.get(Family, tr.family_id)
    d = backoffice.roadbook(world, tr.id)
    text = pdf_text(d.data["roadbook"])
    assert fam.surname in text and "24/7" in text and Path(d.data["roadbook"]).exists()
    assert d.data["vouchers"] and all(tenant().reference(tr.id) in pdf_text(v["path"]) for v in d.data["vouchers"])
    assert d.status == "draft"


def test_booking_check_lists_what_is_missing(world):
    res = backoffice.booking_check(world)
    from brain.db import Setting
    files = world.get(Setting, "report:booking_check").value["files"]
    assert res["files"] == len(files) and all("roadbook not made" in f["missing"] for f in files)
    tr = world.get(TripRequest, files[0]["request_id"])
    backoffice.roadbook(world, tr.id)
    backoffice.booking_check(world)
    after = {f["request_id"]: f for f in world.get(Setting, "report:booking_check").value["files"]}
    assert "roadbook not made" not in after[tr.id]["missing"]


def test_files_are_only_for_people_on_the_trip(world):
    from brain.api.app import app
    tr = next(t for t in world.scalars(select(TripRequest)).all() if t.status == "booked")
    d = backoffice.roadbook(world, tr.id)
    name = Path(d.data["roadbook"]).name
    c = TestClient(app)
    other = next(e.id for e in world.scalars(select(__import__("brain.db", fromlist=["Employee"]).Employee)).all()
                 if e.role == "specialist" and e.id != tr.specialist_id and e.team_id != tr.team_id)
    assert c.get(f"/api/files/roadbooks/{name}", headers={"X-Brain-User": tr.specialist_id}).status_code == 200
    assert c.get(f"/api/files/roadbooks/{name}", headers={"X-Brain-User": other}).status_code == 403
    assert c.get("/api/files/roadbooks/..%2Fsecret", headers={"X-Brain-User": tr.specialist_id}).status_code == 404
