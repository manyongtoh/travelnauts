"""Test #11: a proposal while partners are still checking availability. Both options are built; Travelnauts
chooses with one setting (BRAIN_AVAILABILITY_RULE = warn | block). In both, a partner that said 'not available'
stops the proposal until an alternative is chosen."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from brain.agents import partner_desk, proposal
from brain.db import TripRequest
from brain.workflow import CAVEAT, BlockedByCheck, approve_draft


def setup(world):
    tr = world.scalars(select(TripRequest).where(TripRequest.status == "new")).first()
    d = proposal.write_proposal(world, tr.id)
    prs = partner_desk.plan_partner_requests(world, tr.id)
    for pr in prs:
        pr.status = "waiting"
    world.commit()
    return tr, d, prs


def answer(world, prs, available=True):
    for pr in prs:
        pr.status, pr.offer = "answered", {"available": available, "price_eur": 900}
    world.commit()


def test_warn_sends_with_a_caveat_while_partners_check(world, monkeypatch):
    monkeypatch.setenv("BRAIN_AVAILABILITY_RULE", "warn")
    tr, d, prs = setup(world)
    out = approve_draft(world, d.id, "test")
    assert out.status == "approved" and out.final_body.endswith(CAVEAT)


def test_warn_adds_no_caveat_once_everything_is_confirmed(world, monkeypatch):
    monkeypatch.setenv("BRAIN_AVAILABILITY_RULE", "warn")
    tr, d, prs = setup(world)
    answer(world, prs)
    assert CAVEAT not in approve_draft(world, d.id, "test").final_body


def test_block_waits_for_every_partner(world, monkeypatch):
    monkeypatch.setenv("BRAIN_AVAILABILITY_RULE", "block")
    tr, d, prs = setup(world)
    with pytest.raises(BlockedByCheck, match="Wait until all partners confirm"):
        approve_draft(world, d.id, "test")
    answer(world, prs[:-1])
    with pytest.raises(BlockedByCheck):
        approve_draft(world, d.id, "test")
    answer(world, prs)
    assert approve_draft(world, d.id, "test").status == "approved"


def test_block_asks_to_check_availability_first(world, monkeypatch):
    monkeypatch.setenv("BRAIN_AVAILABILITY_RULE", "block")
    tr = world.scalars(select(TripRequest).where(TripRequest.status == "new")).first()
    d = proposal.write_proposal(world, tr.id)
    with pytest.raises(BlockedByCheck, match="Ask the partners"):
        approve_draft(world, d.id, "test")


@pytest.mark.parametrize("rule", ["warn", "block", "off"])
def test_a_partner_that_said_no_always_stops_the_proposal(world, monkeypatch, rule):
    monkeypatch.setenv("BRAIN_AVAILABILITY_RULE", rule)
    tr, d, prs = setup(world)
    answer(world, prs)
    prs[0].offer = {"available": False}
    world.commit()
    with pytest.raises(BlockedByCheck, match="not available"):
        approve_draft(world, d.id, "test")


def test_the_specialist_sees_where_availability_stands(world, monkeypatch):
    monkeypatch.setenv("BRAIN_AVAILABILITY_RULE", "block")
    from brain.api import app as appmod
    appmod._buckets.clear()
    c = TestClient(appmod.app, raise_server_exceptions=False)
    tr, d, prs = setup(world)
    answer(world, prs[:2])
    r = c.get(f"/api/requests/{tr.id}", headers={"X-Brain-User": tr.specialist_id}).json()
    assert r["availability"] == {"asked": len(prs), "confirmed": 2, "not_available": 0, "open": len(prs) - 2, "expired": 0, "rule": "block"}
    a = c.post(f"/api/drafts/{d.id}/approve", json={}, headers={"X-Brain-User": tr.specialist_id})
    assert a.status_code == 422 and "partners confirm" in a.json()["detail"]
