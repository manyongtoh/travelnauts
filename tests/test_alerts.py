"""The automated morning check: alerts appear, are sent once, clear again, and carry no customer data."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from brain import alerts, auditchain, jobs
from brain.clock import utcnow
from brain.db import AuditEntry, Employee, Family, Job, Setting, TripRequest


@pytest.fixture()
def webhook(monkeypatch):
    got = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("BRAIN_ALERT_WEBHOOK", f"http://127.0.0.1:{srv.server_port}/hook")
    yield got
    srv.shutdown()


def keys(s):
    return {a.key for a in alerts.checks(s)}


def test_a_quiet_system_has_no_alerts(world):
    assert keys(world) == set()


def test_each_problem_raises_its_alert(world):
    for i in range(5):
        jobs.enqueue(world, "triage_mail", {"mail_id": f"x{i}"})
    world.flush()
    world.execute(update(Job).values(status="failed", error="boom"))
    world.add(Setting(key="budget_cap_eur", value=0.0001))
    from brain.db import ModelCall
    world.add(ModelCall(task="triage", model="m", tier="small", ok=True, ms=1, cost_eur=0.01, created_at=utcnow()))
    spec = world.scalars(select(TripRequest).where(TripRequest.status == "new")).first().specialist_id
    world.get(Employee, spec).active = False
    world.commit()
    got = {a.key: a for a in alerts.checks(world)}
    assert got["failed_jobs"].level == "critical"
    assert got["budget"].level == "critical"
    assert "ownerless" in got


def test_a_stopped_scheduler_and_a_broken_chain_are_critical(world):
    from datetime import timedelta
    world.add(Setting(key="last_run:poll_inbox", value=(utcnow() - timedelta(hours=2)).isoformat()))
    auditchain.append(world, "t", "x", "y", "1")
    world.commit()
    world.execute(update(AuditEntry).values(actor="someone-else"))
    world.commit()
    got = {a.key: a.level for a in alerts.checks(world)}
    assert got["scheduler"] == "critical" and got["audit_chain"] == "critical"


def test_alerts_are_sent_once_and_cleared(world, webhook):
    jobs.enqueue(world, "triage_mail", {"mail_id": "x"})
    world.flush()
    world.execute(update(Job).values(status="failed", error="boom"))
    world.commit()
    assert alerts.notify(world)["new"] == 1 and len(webhook) == 1
    assert "failed job" in webhook[0]["text"]
    assert alerts.notify(world)["new"] == 0 and len(webhook) == 1  # still open: not sent again
    world.execute(update(Job).values(status="done"))
    world.commit()
    assert alerts.notify(world)["cleared"] == 1 and "RESOLVED" in webhook[-1]["text"]


def test_alert_texts_carry_no_customer_data(world, webhook):
    for f in world.scalars(select(Family)).all()[:3]:
        jobs.enqueue(world, "write_proposal", {"family": f.surname})
    world.flush()
    world.execute(update(Job).values(status="failed", error="family name inside the error"))
    world.commit()
    alerts.notify(world)
    surnames = [f.surname for f in world.scalars(select(Family)).all()]
    assert not any(n in webhook[0]["text"] for n in surnames)
    assert "family name inside the error" not in webhook[0]["text"]


def test_a_dead_webhook_never_stops_the_brain(world, monkeypatch):
    monkeypatch.setenv("BRAIN_ALERT_WEBHOOK", "http://127.0.0.1:9/nothing-here")
    jobs.enqueue(world, "x", {})
    world.flush()
    world.execute(update(Job).values(status="failed"))
    world.commit()
    assert alerts.notify(world)["delivered"] is False


def test_retry_all_failed_is_admin_only_and_logged(world):
    from brain.api import app as appmod
    appmod._buckets.clear()
    c = TestClient(appmod.app, raise_server_exceptions=False)
    es = world.scalars(select(Employee)).all()
    admin = next(e.id for e in es if e.role == "admin")
    lead = next(e.id for e in es if e.role == "team_lead")
    for i in range(3):
        jobs.enqueue(world, "triage_mail", {"mail_id": f"x{i}"})
    world.flush()
    world.execute(update(Job).values(status="failed"))
    world.commit()
    assert c.post("/api/admin/jobs/retry-failed", headers={"X-Brain-User": lead}).status_code == 403
    assert c.get("/api/admin/alerts", headers={"X-Brain-User": lead}).status_code == 403
    assert c.get("/api/admin/alerts", headers={"X-Brain-User": admin}).json()[0]["key"] == "failed_jobs"
    assert c.post("/api/admin/jobs/retry-failed", headers={"X-Brain-User": admin}).json() == {"requeued": 3}
    world.expire_all()
    assert world.scalars(select(AuditEntry).where(AuditEntry.action == "retry_failed_jobs")).first() is not None
    assert c.get("/api/admin/alerts", headers={"X-Brain-User": admin}).json() == []


def test_the_scheduler_runs_the_check_every_15_minutes(world):
    assert jobs.SCHEDULE["alerts"][1] == 15
    assert "alerts" in jobs.schedule_tick(world)


def test_a_zero_budget_counts_as_reached(world):
    world.add(Setting(key="budget_cap_eur", value=0.0))
    world.commit()
    assert {a.key: a.level for a in alerts.checks(world)}["budget"] == "critical"


def test_budget_waits_are_not_reported_as_agent_failures(world):
    from brain.db import AgentRun
    for i in range(6):
        world.add(AgentRun(agent="proposal_writer", model="m", input_summary="", sources=[], output_summary="", ms=1, ok=False,
                           error="BudgetExceeded: Daily model budget reached", cost_eur=0, created_at=utcnow()))
    world.commit()
    assert "agent_errors" not in keys(world)
    for i in range(6):
        world.add(AgentRun(agent="proposal_writer", model="m", input_summary="", sources=[], output_summary="", ms=1, ok=False,
                           error="ValueError: bad output", cost_eur=0, created_at=utcnow()))
    world.commit()
    assert "agent_errors" in keys(world)


def test_only_https_webhooks_are_used(world, monkeypatch):
    for bad in ("file:///etc/passwd", "ftp://x.example/a", "http://hooks.example/a"):
        monkeypatch.setenv("BRAIN_ALERT_WEBHOOK", bad)
        assert alerts._allowed(bad) is False
    assert alerts._allowed("https://travelnauts.webhook.office.com/x")
