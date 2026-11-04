"""One family from first mail to next trip, through the API as each role (scripts/journey.py).

Guards the hand-offs: nothing in the flow may depend on someone remembering a step."""
import importlib.util
import os
from pathlib import Path


def run_journey(tmp_path, monkeypatch):
    url = os.getenv("BRAIN_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'journey.db'}"
    monkeypatch.setenv("BRAIN_DATABASE_URL", url)
    monkeypatch.setenv("BRAIN_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("BRAIN_FILES", str(tmp_path / "files"))
    spec = importlib.util.spec_from_file_location("journey", Path(__file__).parents[1] / "scripts" / "journey.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        return {e["what"]: e for e in mod.main()}
    finally:
        from brain import clock, db
        clock.reset()
        db.reset_engine()


def test_a_family_goes_from_first_mail_to_next_trip_without_anyone_remembering_a_step(tmp_path, monkeypatch):
    j = run_journey(tmp_path, monkeypatch)
    # a first mail from an unknown address opens a relation and a request, named from the sign-off
    assert j["matched sender"]["new_relation"] is True
    assert j["triaged"]["request"] and j["triaged"]["specialist"]
    # the proposal is ready before the specialist starts
    assert ("proposal", "draft") in j["drafts after triage"]["drafts"]
    assert j["approves and sends proposal"]["status"] == 200
    # silence: a follow-up; after booking it is withdrawn so nobody sends it by mistake
    assert ("followup", "draft") in j["follow-up after silence"]["drafts"]
    assert ("followup", "rejected") in j["day after booking"]["drafts"]
    # booking: extras offered by themselves; roadbook three weeks out once partners confirmed; flights watched
    assert ("extras", "draft") in j["day after booking"]["drafts"]
    before = j["before departure"]["drafts"]
    assert ("roadbook", "draft") in before and ("trip_alert", "draft") in before
    # a complaint from the same address reaches the team lead, linked to the trip
    assert j["sees complaint"]["linked_request"] == [j["triaged"]["request"]]
    # months after coming home: a next-trip idea
    assert j["next trip idea for this family"]["drafted"] is True
    assert j["jobs failed"]["n"] == 0


def test_family_is_found_by_address_and_named_from_the_sign_off(world):
    from types import SimpleNamespace
    from brain.agents.triage import name_from_sign_off, resolve_family
    from brain.db import Family
    known = world.query(Family).filter(Family.email.is_not(None)).first()
    res = SimpleNamespace(category="change", adults=None, child_ages=[])
    assert resolve_family(world, known.email.upper(), res).id == known.id  # case does not matter
    assert resolve_family(world, "nobody@x.example", res) is None  # unknown and not a new request: a person links it
    new = resolve_family(world, "nieuw@x.example", SimpleNamespace(category="new_request", adults=2, child_ages=[6]),
                         "Hoi!\n\nGroeten,\nJan van der Berg\nVerstuurd vanaf mijn iPhone")
    assert new.id.startswith("f-new-") and new.contact_name == "Jan van der Berg" and new.surname == "van der Berg"
    assert name_from_sign_off("Groeten, de familie Jansen") == ("", "")  # not a name: better none than wrong


def test_a_follow_up_cannot_be_sent_after_the_family_booked(world):
    import pytest
    from brain.agents import proposal
    from brain.db import Draft, TripRequest
    from brain.workflow import BlockedByCheck, approve_draft
    tr = world.query(TripRequest).filter(TripRequest.status == "new").first()
    approve_draft(world, proposal.write_proposal(world, tr.id).id, "test")
    d = Draft(kind="followup", request_id=tr.id, title="Nog vragen?", body="Hebben jullie al besloten?", status="draft")
    world.add(d)
    world.commit()
    tr.status = "booked"
    world.commit()
    with pytest.raises(BlockedByCheck, match="no longer needed|No longer needed"):
        approve_draft(world, d.id, "test")


def test_go_live_does_not_flood_old_bookings_with_drafts(world):
    """On the first run the booking check sees every booked trip in TravelSpirit. Only trips still to come get work."""
    from datetime import timedelta
    from brain import jobs
    from brain.agents import backoffice
    from brain.clock import today
    from brain.db import Job, TripRequest
    booked = world.query(TripRequest).filter(TripRequest.status == "booked").all()
    past, soon, later = booked[0], booked[1], booked[2]
    past.depart_date, soon.depart_date, later.depart_date = today() - timedelta(days=200), today() + timedelta(days=10), today() + timedelta(days=90)
    for t in booked[3:]:
        t.depart_date = today() - timedelta(days=400)
    world.commit()
    backoffice.booking_check(world)
    queued = {(j.kind, j.payload.get("request_id")) for j in world.query(Job).filter(Job.status == "queued").all()}
    assert ("extras", later.id) in queued                     # time enough to add extras
    assert ("extras", soon.id) not in queued                  # too late for extras
    assert not any(rid == past.id for _, rid in queued)       # already travelled: nothing
    assert sum(k == "extras" for k, _ in queued) == 1
