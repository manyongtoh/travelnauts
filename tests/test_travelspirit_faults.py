"""Test #5: TravelSpirit slow, flaky or down.

What must hold: no mail is lost or handled twice, nothing is half saved, jobs wait instead of failing, TravelSpirit
is not hammered while it is down, and someone is told when it stays down."""
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select, update

from brain import alerts, clock, jobs
from brain.db import AgentRun, Draft, Job, Mail, Setting, ToolCall, TripRequest

T0 = datetime(2026, 11, 9, 9, 0)


def faults(s, value):
    st = s.get(Setting, "ts_faults")
    if st:
        st.value = value
    else:
        s.add(Setting(key="ts_faults", value=value))
    s.commit()


def run(s, start, minutes, step=5):
    t = start
    while t < start + timedelta(minutes=minutes):
        clock.set_now(t)
        jobs.schedule_tick(s)
        for _ in range(5):
            if not jobs.work(s, limit=200):
                break
        t += timedelta(minutes=step)
    return t


def settle(s, start):
    faults(s, None)
    return run(s, start, 240, step=20)


def check_nothing_lost_or_doubled(s):
    assert s.query(Mail).filter(Mail.status == "new").count() == 0
    triaged = Counter(r.subject for r in s.scalars(select(AgentRun).where(AgentRun.agent == "triage", AgentRun.ok.is_(True))).all())
    assert not [k for k, v in triaged.items() if v > 1], "a mail was triaged twice"
    assert s.query(Job).filter(Job.status == "failed").count() == 0, \
        [(j.kind, j.error) for j in s.query(Job).filter(Job.status == "failed").all()][:3]
    # every new request has exactly one proposal draft: nothing half saved, nothing doubled
    for tr in s.scalars(select(TripRequest).where(TripRequest.status == "proposal_draft")).all():
        assert s.query(Draft).filter(Draft.request_id == tr.id, Draft.kind == "proposal").count() == 1, tr.id


def test_a_flaky_travelspirit_loses_nothing(world):
    try:
        faults(world, {"mode": "flaky", "rate": 0.3, "seed": 1})
        t = run(world, T0, 120)
        assert world.query(ToolCall).filter(ToolCall.tool.like("ts.%"), ToolCall.ok.is_(False)).count() > 0  # faults happened
        settle(world, t)
        check_nothing_lost_or_doubled(world)
    finally:
        clock.reset()


def test_a_slow_travelspirit_times_out_and_recovers(world):
    try:
        faults(world, {"mode": "slow", "rate": 0.5, "seed": 2})
        t = run(world, T0, 90)
        settle(world, t)
        check_nothing_lost_or_doubled(world)
    finally:
        clock.reset()


def test_two_hours_down_nothing_fails_it_is_not_hammered_and_someone_is_told(world):
    try:
        faults(world, {"mode": "down"})
        before = world.query(ToolCall).count()
        t = run(world, T0, 120)
        calls = world.query(ToolCall).count() - before
        assert calls <= 24 * 3, f"{calls} calls to a TravelSpirit that is down: that is hammering"  # about one try per pass
        assert world.query(Job).filter(Job.status == "failed").count() == 0
        clock.set_now(t)
        got = {a.key: a.level for a in alerts.checks(world)}
        assert got.get("travelspirit") == "critical"  # down for over an hour
        t = settle(world, t)
        clock.set_now(t)
        assert "travelspirit" not in {a.key for a in alerts.checks(world)}
        check_nothing_lost_or_doubled(world)
    finally:
        clock.reset()


def test_after_twelve_hours_a_waiting_job_fails_and_is_reported(world):
    try:
        clock.set_now(T0)
        jobs.enqueue(world, "triage_mail", {"mail_id": world.scalars(select(Mail).where(Mail.status == "new")).first().id})
        world.commit()
        world.execute(update(Job).values(created_at=T0 - timedelta(hours=13)))
        world.commit()
        faults(world, {"mode": "down"})
        for i in range(4):  # after its patience is used up, the normal three tries apply
            clock.set_now(T0 + timedelta(minutes=30 * i))
            jobs.work(world, limit=50)
        assert world.query(Job).filter(Job.status == "failed").count() >= 1
        assert "failed_jobs" in {a.key for a in alerts.checks(world)}
    finally:
        clock.reset()


def test_faults_can_only_be_switched_on_in_the_test_environment(world, monkeypatch):
    from brain.connectors import (
        Channel,
        SystemOfRecord,
        get_channel,
        get_system_of_record,
    )
    from brain.travelspirit.client import FakeTravelSpirit, FakeTravelSpiritMail
    faults(world, {"mode": "down"})
    monkeypatch.setenv("BRAIN_ENV", "pilot")
    assert type(get_system_of_record(world)) is FakeTravelSpirit and type(get_channel(world)) is FakeTravelSpiritMail
    assert isinstance(get_system_of_record(world), SystemOfRecord) and isinstance(get_channel(world), Channel)
