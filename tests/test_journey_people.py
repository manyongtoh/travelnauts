"""A specialist's day and a team lead's day (scripts/journey_people.py), and the fixes behind them."""
import importlib.util
import os
from pathlib import Path


def run(tmp_path, monkeypatch):
    url = os.getenv("BRAIN_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'p.db'}"
    for k, v in (("BRAIN_DATABASE_URL", url), ("BRAIN_VAULT", str(tmp_path / "v")), ("BRAIN_FILES", str(tmp_path / "f"))):
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("jp", Path(__file__).parents[1] / "scripts" / "journey_people.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        return {e["what"]: e for e in mod.main()}
    finally:
        from brain import clock, db
        clock.reset()
        db.reset_engine()


def test_specialist_and_team_lead_day(tmp_path, monkeypatch):
    j = run(tmp_path, monkeypatch)
    # the specialist's morning: everything is drafted before she looks
    assert j["proposal for the new family waiting"]["ready"]
    assert j["edits and sends the proposal"]["status"] == 200 and 0 < j["edits and sends the proposal"]["edit_share"] < 0.3
    # "a night less in Bangkok" is a change request even when the model calls it a question, and the new version waits
    assert j["change request drafted by itself"]["ready"] and j["sends the changed proposal"]["status"] == 200
    # a question from a family with an open trip is tied to that trip
    assert j["question triaged"]["request"]
    assert j["tries to send the placeholder"]["status"] == 422 and j["sends the answer"]["status"] == 200
    assert j["asks the brain something it does not know"]["gap"]
    # a family stranded at the airport: urgent, on the trip they are on, high, and the team lead sends the reply
    urgent = j["urgent complaint handled how"]
    assert urgent["category"] == "complaint" and urgent["urgent"] and urgent["right_trip"]
    seen = j["opens the overview"]
    assert seen["complaint_seen"] and seen["complaint"] == "high" and seen["travelling"]
    assert j["tries to send the urgent complaint reply"]["status"] == 403
    assert j["approves the complaint reply"]["status"] == 200
    # mail from an unknown address waits for a person, then flows on
    assert "p-unknown" in seen["unknown_address"] and j["after linking"]["request"]
    # sick for a week: the colleague gets the requests and their drafts, nothing is left addressed to her
    moved = j["moves Sanne's open requests to a colleague"]
    assert moved["ok"] == moved["requests"] and moved["colleague_sees"] == moved["drafts_waiting"] and moved["sanne_still_sees"] == 0
    assert j["drafts still addressed to Sanne after the move"]["n"] == 0
    assert j["reads the gap list"]["laos"]
    # a leaver: the orphaned work shows for the team lead and raises an alert
    assert j["sees work without an owner"]["ownerless"] >= 1 and "ownerless" in j["sees work without an owner"]["alert"]
    assert j["end of day"]["failed_jobs"] == 0


def test_road_alert_after_thirty_minutes(world):
    from datetime import timedelta

    from brain import alerts
    from brain.clock import utcnow
    from brain.db import Draft
    world.add(Draft(kind="complaint_reply", title="x", body="x", data={"while_travelling": True}, created_at=utcnow() - timedelta(minutes=10)))
    world.commit()
    assert "travelling_family" not in {a.key for a in alerts.checks(world)}
    assert "travelling_family" in {a.key for a in alerts.checks(world, utcnow() + timedelta(minutes=25))}
