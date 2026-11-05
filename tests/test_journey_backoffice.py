"""The back office journey (scripts/journey_backoffice.py) and the checks behind it."""
import importlib.util
import os
from pathlib import Path

import pytest
from brain.tenant import tenant


def run(tmp_path, monkeypatch):
    url = os.getenv("BRAIN_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'bo.db'}"
    for k, v in (("BRAIN_DATABASE_URL", url), ("BRAIN_VAULT", str(tmp_path / "v")), ("BRAIN_FILES", str(tmp_path / "f"))):
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("jbo", Path(__file__).parents[1] / "scripts" / "journey_backoffice.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        return {e["what"]: e for e in mod.main()}
    finally:
        from brain import clock, db
        clock.reset()
        db.reset_engine()


def test_the_back_office_day_for_one_trip(tmp_path, monkeypatch):
    j = run(tmp_path, monkeypatch)
    # replies from real addresses, with and without our reference, are read and land on the right request
    for mid in ("bo-r1", "bo-r2", "bo-r3"):
        assert j[f"partner reply {mid}"]["category"] == "partner_reply" and j[f"partner reply {mid}"]["partner"]
    statuses = [j[w]["status"] for w in j if w.startswith("request to ")]
    assert statuses.count("answered") == 1 and statuses.count("declined") == 1 and statuses.count("unclear") == 1
    confirmed = next(j[w] for w in j if w.startswith("request to ") and j[w]["status"] == "answered")
    assert confirmed["offer"]["price_eur"] == 1240.0  # "EUR 1.240" is twelve hundred and forty euro
    # a 'no' brings alternatives; 'we will come back to you' is not counted as a yes
    assert j["alternative for the partner that said no"]["drafted"] is True
    assert j["sees availability"]["availability"]["confirmed"] == 1
    # only the partners that are silent get reminders, and silence after a reminder is flagged
    assert j["chase mails drafted"]["n"] == 2
    assert any("silent after a reminder" in m for m in j["booking file check"]["missing"])
    # invoices: the right offer, the duplicate caught, the silent partner's invoice not matched to anything
    assert j["invoice bo-i1"]["status"] == "match" and j["invoice bo-i1"]["expected"] == 1240.0
    assert j["invoice bo-i2"]["status"] == "duplicate"
    assert j["invoice bo-i3"]["status"] == "unknown"
    assert j["jobs failed"]["n"] == 0


@pytest.mark.parametrize("raw,want", [("1.240", 1240), ("1,240", 1240), ("1.240,50", 1240.5), ("1,240.50", 1240.5),
                                      ("1240,50", 1240.5), ("99.95", 99.95), ("12.500.000", 12500000), ("250,-", 250)])
def test_euro_amounts_are_read_the_way_people_write_them(raw, want):
    from brain.money import parse_amount
    assert parse_amount(raw) == want


def test_the_price_check_reads_european_amounts(world):
    from brain.guardrails import check_output
    assert check_output("Totaal € 4.890,00 voor het hele gezin.", [4890]) == []
    assert check_output("Totaal € 4.890,00 voor het hele gezin.", [4980])  # a different price is caught


def test_a_misread_invoice_amount_is_sent_to_a_person(world, monkeypatch):
    from brain import sandbox_model
    from brain.agents import backoffice
    from brain.clock import utcnow
    from brain.db import Mail
    orig = sandbox_model.HANDLERS["invoice_extract"]
    monkeypatch.setitem(sandbox_model.HANDLERS, "invoice_extract", lambda ctx: orig(ctx) | {"amount_eur": 1.24})
    world.add(Mail(id="inv-x", received_at=utcnow(), sender="accounts@x.example", subject=f"Invoice 9 {tenant().reference('r001')}",
                   body=f"Invoice 9\nReference {tenant().reference('r001')}\nTotal EUR 1.240", status="triaged", truth={}))
    world.commit()
    chk = backoffice.invoices(world, "inv-x")
    assert chk.status == "check" and "1240" in chk.note


def test_a_replaced_hotel_no_longer_blocks_the_trip(world):
    from sqlalchemy import select
    from brain.agents import partner_desk, proposal
    from brain.db import Draft, Partner, TripRequest
    from brain.workflow import availability
    tr = world.scalars(select(TripRequest).where(TripRequest.status == "new")).first()
    d = proposal.write_proposal(world, tr.id)
    prs = partner_desk.plan_partner_requests(world, tr.id)
    hotel_pr = next(pr for pr in prs if world.get(Partner, pr.partner_id).kind == "hotel")
    for pr in prs:
        pr.status, pr.offer = "answered", {"available": True, "price_eur": 900}
    hotel_pr.status, hotel_pr.offer = "declined", {"available": False}
    world.commit()
    assert availability(world, tr.id)["not_available"] == 1
    old = world.get(Partner, hotel_pr.partner_id).name
    other = world.scalars(select(Partner).where(Partner.kind == "hotel", Partner.name != old)).first()
    route = [dict(r, hotel=other.name) if r["hotel"] == old else r for r in d.data["route"]]
    world.add(Draft(kind="change", request_id=tr.id, title="Ander hotel", body="x", status="approved", data={"route": route, "price": d.data["price"]}))
    world.commit()
    assert availability(world, tr.id)["not_available"] == 0  # the declined hotel is off the route now
