"""Automatic send: asked after ten unchanged approvals, 10 seconds to stop, every check still applies."""
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_api import LEAD, RUBEN, SANNE


def _setup(world):
    from brain.api import app as appmod
    from brain.db import TripRequest
    appmod._buckets.clear()  # many approvals in a row: start each test with a fresh rate limit
    c = TestClient(appmod.app)
    c.post("/api/triage", headers=SANNE)
    tr = world.scalars(select(TripRequest).where(TripRequest.specialist_id == "sanne-de-vries")).first()
    tr.status = "proposal_sent"  # follow-ups are only valid while the family has a proposal and has not answered
    world.commit()
    return c, tr


def _draft(s, tr, kind="followup", body="Hallo,\n\nHebben jullie al naar het voorstel kunnen kijken?\n\nGroet, Sanne"):
    from brain.db import Draft
    d = Draft(kind=kind, request_id=tr.id, title=f"{kind} {tr.id}", body=body, data={})
    s.add(d)
    s.commit()
    return d.id


def test_ask_after_ten_unchanged_then_countdown_stop_and_send(world):
    from brain import autosend
    from brain.clock import utcnow
    from brain.db import AuditEntry, Draft
    c, tr = _setup(world)
    for i in range(9):
        r = c.post(f"/api/drafts/{_draft(world, tr)}/approve", json={}, headers=SANNE).json()
        assert r["ask_autosend"] is None
    edited = _draft(world, tr)  # one change resets the count
    c.post(f"/api/drafts/{edited}/approve", json={"final_body": "Hoi,\n\nNog vragen over het voorstel? Bel gerust.\n\nSanne"}, headers=SANNE)
    assert c.post("/api/autosend/followup", json={"choice": "yes"}, headers=SANNE).status_code == 409  # not offered yet
    for i in range(10):
        r = c.post(f"/api/drafts/{_draft(world, tr)}/approve", json={}, headers=SANNE).json()
    assert r["ask_autosend"]["kind"] == "followup" and r["ask_autosend"]["hold_seconds"] == 10
    assert "10 seconds" in r["ask_autosend"]["text"]
    assert c.get("/api/autosend", headers=SANNE).json()["switches"][0]["ask"]  # shown again after a reload
    assert c.post("/api/autosend/followup", json={"choice": "yes"}, headers=SANNE).json()["status"] == "on"

    # a new follow-up counts down; another specialist cannot stop it; it is not sent early
    did = _draft(world, tr)
    mine = c.get("/api/autosend", headers=SANNE).json()
    assert [x["id"] for x in mine["counting"]] == [did] and 0 < mine["counting"][0]["seconds_left"] <= 10
    assert c.post(f"/api/drafts/{did}/send-due", headers=SANNE).status_code == 409
    assert c.post(f"/api/drafts/{did}/stop", headers=RUBEN).status_code == 403
    assert c.post(f"/api/drafts/{did}/stop", headers=SANNE).status_code == 200
    world.expire_all()
    assert autosend.run_due(world, utcnow() + timedelta(seconds=11))["sent"] == 0
    assert world.get(Draft, did).status == "draft"  # stopped: waits for Sanne

    # the next one goes out by itself after 10 seconds, logged as automatic
    did2 = _draft(world, tr)
    assert autosend.run_due(world, utcnow() + timedelta(seconds=5))["sent"] == 0
    assert autosend.run_due(world, utcnow() + timedelta(seconds=11))["sent"] == 1
    d2 = world.get(Draft, did2)
    world.refresh(d2)
    assert d2.status == "approved" and d2.decided_by.startswith("auto:")
    assert world.scalars(select(AuditEntry).where(AuditEntry.action == "approve", AuditEntry.object_id == str(did2))).first().actor.startswith("auto:")
    assert c.get("/api/value", headers=LEAD).json()["quality"]["per_kind"]["followup"]["auto_sent"] == 1

    # checks still apply: a price nobody calculated blocks the send and it waits for the person
    bad = _draft(world, tr, body="Hallo,\n\nAls jullie nu boeken kost het maar € 4.999.\n\nSanne")
    assert autosend.run_due(world, utcnow() + timedelta(seconds=11)) == {"sent": 0, "blocked": 1}
    b = world.get(Draft, bad)
    world.refresh(b)
    assert b.status == "draft" and "Price" in b.data["auto_blocked"]

    # proposals are never automatic, whatever the history
    prop = _draft(world, tr, kind="proposal")
    assert autosend.send_at(world, world.get(Draft, prop)) is None

    # switched off: new drafts wait again
    c.post("/api/autosend/followup", json={"choice": "off"}, headers=SANNE)
    off = _draft(world, tr)
    assert autosend.run_due(world, utcnow() + timedelta(seconds=11))["sent"] == 0 and world.get(Draft, off).status == "draft"


def test_saying_no_waits_longer_and_desk_kinds_need_back_office(world):
    from brain import autosend
    c, tr = _setup(world)
    for i in range(10):
        r = c.post(f"/api/drafts/{_draft(world, tr)}/approve", json={}, headers=SANNE).json()
    assert r["ask_autosend"]
    c.post("/api/autosend/followup", json={"choice": "no"}, headers=SANNE)
    for i in range(10):
        r = c.post(f"/api/drafts/{_draft(world, tr)}/approve", json={}, headers=SANNE).json()
    assert r["ask_autosend"] is None  # after a no, it waits for 30 more
    assert c.post("/api/autosend/partner_request", json={"choice": "yes"}, headers=SANNE).status_code == 403
    assert c.post("/api/autosend/proposal", json={"choice": "yes"}, headers=SANNE).status_code == 409
    assert autosend.state(world, autosend.DESK, "partner_request")["status"] == "none"
