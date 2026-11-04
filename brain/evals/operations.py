"""Two weeks of daily operation in a few minutes, with things going wrong on purpose.

  brain simulate --days 14            (best on Postgres, so the database restart can be tested)

Every simulated working day: new family mails and partner replies arrive in the morning, the scheduler and
workers run every hour, specialists write and approve proposals (with edits), the back office sends partner
requests, team leads approve knowledge, and the nightly jobs run at 02:00. On set days something breaks:

  day 3   a worker dies in the middle of a job
  day 5   the model is down: first with a fallback model, then without
  day 7   the database restarts (Postgres only)
  day 9   the daily model budget runs out
  day 11  a specialist leaves the company
  day 13  a knowledge note is changed in the vault

Each day records what happened, and checks that the queue drains, nothing is processed twice, failed work
recovers, logs stay bounded by retention, and the audit chain stays intact.
"""
from __future__ import annotations

import os
import random
import subprocess
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select


def _pg_restart(url: str) -> str:
    """Restart the local test Postgres (only when it is the one this sandbox started)."""
    data = os.getenv("BRAIN_SIM_PGDATA")
    if not data or "postgresql" not in url:
        return "skipped (not a local Postgres)"
    b = "/usr/lib/postgresql/16/bin/pg_ctl"
    home = os.path.dirname(os.path.abspath(data))  # socket and log sit next to the data folder this sandbox made
    subprocess.run(["runuser", "-u", "postgres", "--", b, "-D", data, "-m", "fast", "restart", "-o",
                    f"-p 5433 -k {home} -c max_connections=200", "-l", os.path.join(home, "log"), "-w"],
                   check=True, capture_output=True)
    return "restarted"


def run(days: int = 14, seed: int = 7, mails_per_day: int = 25) -> dict:
    from .. import auditchain, clock, db, jobs
    from ..agents import partner_desk, proposal
    from ..db import (AgentRun, Draft, Employee, Family, Job, KnowledgeItem, Mail, ModelCall, PartnerRequest, Setting,
                      ToolCall, TripRequest)
    from ..knowledge import vault
    from ..synth.generate import build
    from ..synth.world import DESTINATIONS
    from ..workflow import approve_draft

    rng = random.Random(seed)
    url = os.environ.get("BRAIN_DATABASE_URL", "")
    start = datetime(2026, 11, 9, 7, 0)  # a Monday
    clock.set_now(start - timedelta(days=1))
    build(seed, hard=False)
    os.environ["BRAIN_RETENTION_DAYS"] = "7"
    report = {"database": "postgres" if "postgresql" in url else "sqlite", "days": []}
    mail_no = 0
    day_alerts: dict[str, str] = {}

    def tick(hour_dt: datetime) -> list[dict]:
        from .. import alerts
        clock.set_now(hour_dt)
        with db.session() as s:
            jobs.schedule_tick(s)
            out = []
            for _ in range(20):
                done = jobs.work(s, limit=100)
                out += done
                if not done:
                    break
            for a in alerts.checks(s):  # the 15-minute check, after this tick's work (ticks here are hourly)
                day_alerts.setdefault(a.key, a.level)
            return out

    def new_mails(s, day: datetime, n: int) -> int:
        nonlocal mail_no
        fams = list(s.scalars(select(Family)).all())
        months = ["januari", "maart", "april", "mei", "juli", "augustus", "oktober"]
        for _ in range(n):
            mail_no += 1
            f = rng.choice(fams)
            dest = rng.choice(list(DESTINATIONS))
            ages = " en ".join(str(a) for a in f.child_ages)
            s.add(Mail(id=f"sim{mail_no:05d}", received_at=day + timedelta(minutes=rng.randint(0, 120)), sender=f.email,
                       subject=f"Aanvraag {DESTINATIONS[dest]['nl']}",
                       body=f"Hallo,\n\nWij willen graag in {rng.choice(months)} naar {DESTINATIONS[dest]['nl']}, {rng.choice([14, 18, 21])} dagen.\n"
                            f"We zijn met {f.adults} volwassenen en {len(f.child_ages)} kinderen ({ages} jaar).\n\nGroet, {f.contact_name}",
                       family_id=f.id, truth={"category": "new_request", "set": "sim"}))
        # partners answer some open requests
        for pr in s.scalars(select(PartnerRequest).where(PartnerRequest.status.in_(["waiting", "chased"]))).all():
            if rng.random() < 0.35:
                mail_no += 1
                p = s.get(__import__("brain.db", fromlist=["Partner"]).Partner, pr.partner_id)
                ok = rng.random() < 0.85
                s.add(Mail(id=f"sim{mail_no:05d}", received_at=day + timedelta(minutes=rng.randint(0, 120)), sender=p.email,
                           subject=f"RE: Availability request TN-{pr.request_id.upper()}", partner_id=p.id, truth={"category": "partner_reply"},
                           body=("Dear team,\n\nWe confirm availability, family room, EUR " + str(rng.choice([780, 920, 1100])) + ".\n\nRegards")
                           if ok else "Dear team,\n\nUnfortunately we are fully booked.\n\nRegards"))
        s.commit()
        return n

    def staff_work(s, day: datetime) -> dict:
        made = approved = sent = 0
        # specialists write proposals for new requests and approve most drafts, often with edits
        for tr in s.scalars(select(TripRequest).where(TripRequest.status == "new", TripRequest.mail_id.is_not(None))).all()[:15]:
            try:
                proposal.write_proposal(s, tr.id)
                made += 1
            except Exception:  # noqa: BLE001
                s.rollback()
        for d in s.scalars(select(Draft).where(Draft.status == "draft", Draft.kind.in_(["proposal", "followup", "change"]))).all():
            if rng.random() < 0.7:
                tr = s.get(TripRequest, d.request_id) if d.request_id else None
                spec = tr.specialist_id if tr else "sanne-de-vries"
                body = d.body + ("\n\nPS Ik bel jullie morgen even." if rng.random() < 0.5 else "")
                try:
                    approve_draft(s, d.id, spec, body, actor_id=spec)
                    approved += 1
                except Exception:  # noqa: BLE001
                    s.rollback()
        # back office asks partners for approved proposals and sends drafted partner mails
        for tr in s.scalars(select(TripRequest).where(TripRequest.status == "proposal_sent")).all()[:6]:
            try:
                partner_desk.plan_partner_requests(s, tr.id)
            except Exception:  # noqa: BLE001
                s.rollback()
        for d in s.scalars(select(Draft).where(Draft.status == "draft", Draft.kind.in_(["partner_request", "partner_chase"]))).all():
            approve_draft(s, d.id, "ruben-stam", actor_id="ruben-stam")
            sent += 1
        # specialists send the extras offers and handle trip alerts; back office sends roadbooks; leads answer complaints
        lead_of = {e.team_id: e.id for e in s.scalars(select(Employee).where(Employee.role == "team_lead")).all()}
        for d in s.scalars(select(Draft).where(Draft.status == "draft", Draft.kind == "answer")).all():
            tr = s.get(TripRequest, d.request_id) if d.request_id else None
            who = tr.specialist_id if tr else "sanne-de-vries"
            body = d.body if "[Schrijf hier" not in d.body else (
                "Goede vraag. Dat hebben we voor jullie nagevraagd bij onze lokale partner: het kan, we regelen het "
                "bij de boeking en zetten het in het reisboek.")
            try:
                approve_draft(s, d.id, who, body, actor_id=who)
                approved += 1
            except Exception:  # noqa: BLE001
                s.rollback()
        for d in s.scalars(select(Draft).where(Draft.status == "draft", Draft.kind.in_(
                ["extras", "trip_alert", "next_trip", "roadbook", "complaint_reply"]))).all():
            if rng.random() < 0.8:
                tr = s.get(TripRequest, d.request_id) if d.request_id else None
                who = {"roadbook": "ruben-stam"}.get(d.kind) or (lead_of.get(tr.team_id) if d.kind == "complaint_reply" and tr else None) \
                    or (tr.specialist_id if tr else "sanne-de-vries")
                try:
                    approve_draft(s, d.id, who, actor_id=who)
                    approved += 1
                except Exception:  # noqa: BLE001
                    s.rollback()
        # some families book
        for tr in s.scalars(select(TripRequest).where(TripRequest.status == "proposal_sent")).all():
            if rng.random() < 0.08:
                tr.status = "booked"
                tr.depart_date = (day + timedelta(days=rng.randint(1, 60))).date()
                tr.flights = [{"number": f"KL{rng.randint(100, 999)}", "date": tr.depart_date.isoformat(), "from": "AMS", "to": "BKK"}]
        s.commit()
        return {"proposals_written": made, "drafts_approved": approved, "partner_mails_sent": sent}

    for n in range(days):
        day = start + timedelta(days=n)
        weekday = day.weekday()
        events, checks = [], {}
        with db.session() as s:
            if weekday < 5:
                new_mails(s, day, mails_per_day)
        worked = []
        staff = Counter()

        # --- the incidents ---------------------------------------------------------------------
        if n == 2:  # a worker dies in the middle of a job
            clock.set_now(day.replace(hour=9))
            with db.session() as s:
                j = jobs.enqueue(s, "poll_inbox")
                s.commit()
                jobs.claim(s, "dying-worker", 1000)  # claims everything, then never finishes
                stuck = s.query(Job).filter(Job.status == "running").count()
            events.append(f"worker died holding {stuck} jobs at 09:00")
            worked += tick(day.replace(hour=9, minute=5))
            with db.session() as s:
                checks["jobs_still_stuck_after_5_min"] = s.query(Job).filter(Job.status == "running").count()
            worked += tick(day.replace(hour=9, minute=20))  # lease (10 min) has run out: jobs come back
            with db.session() as s:
                checks["jobs_stuck_after_20_min"] = s.query(Job).filter(Job.status == "running").count()
        if n == 3:  # TravelSpirit down for two and a half hours in the morning
            from .. import alerts as _alerts
            with db.session() as s:
                s.merge(Setting(key="ts_faults", value={"mode": "down"}))
                s.commit()
                new_mails(s, day.replace(hour=9, minute=30), 8)
            for hh, mm in ((10, 0), (10, 30), (11, 0), (11, 45)):
                worked += tick(day.replace(hour=hh, minute=mm))
            with db.session() as s:
                checks["jobs_failed_while_travelspirit_down"] = s.query(Job).filter(Job.status == "failed").count()
                checks["jobs_waiting_for_travelspirit"] = s.query(Job).filter(Job.status == "queued",
                                                                            Job.error.like("waiting for TravelSpirit%")).count()
                checks["travelspirit_alert"] = next((a.level for a in _alerts.checks(s) if a.key == "travelspirit"), "none")
                s.merge(Setting(key="ts_faults", value=None))
                s.commit()
            events.append("TravelSpirit down 09:30 to 12:00")
        if n == 4:  # model outage
            os.environ["BRAIN_MODEL_SMALL"] = "test:broken"
            os.environ["BRAIN_MODEL_LARGE"] = "test:broken"
            os.environ["BRAIN_MODEL_FALLBACK"] = "sandbox"
            worked += tick(day.replace(hour=9))
            with db.session() as s:
                checks["failed_jobs_with_fallback"] = s.query(Job).filter(Job.status == "failed").count()
            os.environ["BRAIN_MODEL_FALLBACK"] = ""
            with db.session() as s:
                new_mails(s, day.replace(hour=10), 10)
            for h in (10, 11):
                worked += tick(day.replace(hour=h))
            with db.session() as s:
                checks["failed_or_waiting_without_fallback"] = s.query(Job).filter(Job.status.in_(["failed", "queued"])).count()
            for k in ("BRAIN_MODEL_SMALL", "BRAIN_MODEL_LARGE"):
                os.environ.pop(k, None)
            events.append("model down 09:00 to 12:00 (fallback for the first hour only)")
            with db.session() as s:  # the admin retries failed jobs from the maintenance screen
                retried = 0
                for j in s.scalars(select(Job).where(Job.status == "failed")).all():
                    j.status, j.attempts, j.error, j.run_after = "queued", 0, None, clock.utcnow()
                    retried += 1
                s.commit()
            events.append(f"admin retried {retried} failed jobs at 12:00")
        if n == 6:
            events.append("database " + _pg_restart(url) + " at 11:00")
            clock.set_now(day.replace(hour=11))
            from fastapi.testclient import TestClient
            from ..api.app import app
            checks["ready_after_restart"] = TestClient(app).get("/readyz").status_code
        if n == 8:  # budget runs out
            with db.session() as s:
                s.merge(Setting(key="budget_cap_eur", value=0.0))
                s.commit()
                new_mails(s, day.replace(hour=10), 5)
            worked += tick(day.replace(hour=10))
            with db.session() as s:
                checks["jobs_waiting_for_budget"] = s.query(Job).filter(Job.status == "queued").count()
                checks["jobs_failed_on_budget"] = s.query(Job).filter(Job.status == "failed", Job.error.like("BudgetExceeded%")).count()
                s.merge(Setting(key="budget_cap_eur", value=5.0))
                s.commit()
            events.append("daily model budget reached at 10:00, raised again at 10:30")
        if n == 10:  # a specialist leaves
            with db.session() as s:
                e = s.scalars(select(Employee).where(Employee.role == "specialist", Employee.team_id == "asia")).first()
            from fastapi.testclient import TestClient
            from ..api.app import app
            r = TestClient(app).post(f"/api/admin/users/{e.id}", json={"active": False}, headers={"X-Brain-User": "myt-beheer"}).json()
            checks["reassign_list_given_to_admin"] = len(r.get("open_requests_to_reassign", []))
            with db.session() as s:
                checks["open_requests_of_leaver"] = s.query(TripRequest).filter(
                    TripRequest.specialist_id == e.id, TripRequest.status.in_(["new", "proposal_draft", "change_requested"])).count()
            events.append(f"{e.name} left; access removed")
        if n == 11:  # the team lead reassigns the leaver's requests from Team lead > Insight
            from fastapi.testclient import TestClient
            from ..api.app import app
            from ..alerts import OPEN_REQUEST_STATUSES
            with db.session() as s:
                gone = {e.id for e in s.scalars(select(Employee).where(Employee.active.is_(False))).all()}
                todo = s.scalars(select(TripRequest).where(TripRequest.specialist_id.in_(gone),
                                                           TripRequest.status.in_(OPEN_REQUEST_STATUSES))).all()
                lead = {e.team_id: e.id for e in s.scalars(select(Employee).where(Employee.role == "team_lead")).all()}
                pick = {}
                for e in s.scalars(select(Employee).where(Employee.role == "specialist", Employee.active.is_(True))).all():
                    pick.setdefault(e.team_id, e.id)
                todo = [(r.id, r.team_id) for r in todo]
            c = TestClient(app)
            ok = sum(c.post(f"/api/requests/{rid}/reassign", json={"specialist_id": pick[t]},
                            headers={"X-Brain-User": lead[t]}).status_code == 200 for rid, t in todo)
            events.append(f"team lead reassigned {ok} of {len(todo)} requests")
        if n == 12:  # someone edits the vault
            with db.session() as s:
                approved = {k.id for k in s.scalars(select(KnowledgeItem).where(KnowledgeItem.status == "approved")).all()}
            note = next(p for p in sorted(vault.vault_dir().rglob("*.md")) if vault.parse_note(p.read_text())[0].get("id") in approved)
            changed_id = vault.parse_note(note.read_text())[0]["id"]
            was = "approved"
            note.write_text(note.read_text() + "\nAangevuld door de content redactie.\n")
            events.append(f"note {note.name} ({was}) changed in the vault")

        # --- a normal day -----------------------------------------------------------------------
        if weekday < 5:
            for h in range(9, 18):
                worked += tick(day.replace(hour=h))
                if h in (10, 14):
                    with db.session() as s:
                        staff.update(staff_work(s, day.replace(hour=h)))
        worked += tick((day + timedelta(days=1)).replace(hour=2))  # nightly jobs
        if n == 12:
            with db.session() as s:
                item = s.get(KnowledgeItem, changed_id)
                checks["changed_note_status_after_reindex"] = f"{item.status}, change waiting: {item.pending_body is not None}"
                checks["changed_note_findable_by_agents"] = any(h.id == changed_id for h in __import__("brain.knowledge.store", fromlist=["KnowledgeBase"]).KnowledgeBase(s).search(item.title, k=10))
        if n == 10:
            with db.session() as s:
                ti = (s.get(Setting, "report:team_insight") or Setting(key="", value={})).value
                checks["leaver_requests_flagged_by_team_insight"] = sum(len(t.get("ownerless", [])) for t in ti.get("teams", {}).values())

        with db.session() as s:
            report["days"].append({
                "day": n + 1, "date": day.date().isoformat(), "weekday": day.strftime("%a"), "events": events, "checks": checks,
                "jobs_run": len(worked), "staff": dict(staff), "jobs_by_kind": dict(Counter(w["kind"] for w in worked)),
                "failed_jobs_total": s.query(Job).filter(Job.status == "failed").count(),
                "queued_end_of_day": s.query(Job).filter(Job.status == "queued", Job.run_after <= clock.utcnow()).count(),
                "mails_untriaged": s.query(Mail).filter(Mail.status == "new").count(),
                "triaged_twice": sum(1 for v in Counter(r.subject for r in s.scalars(select(AgentRun).where(AgentRun.agent == "triage", AgentRun.ok.is_(True))).all()).values() if v > 1),
                "drafts_waiting": s.query(Draft).filter(Draft.status == "draft").count(),
                "rows": {"tool_calls": s.query(ToolCall).count(), "model_calls": s.query(ModelCall).count(), "agent_runs": s.query(AgentRun).count()},
                "audit_chain_ok": auditchain.verify(s)["ok"],
                "alerts": dict(day_alerts),
                "alerts_open_at_night": [a.key for a in __import__("brain.alerts", fromlist=["checks"]).checks(s)],
            })
        day_alerts.clear()
    clock.reset()
    return report


def to_markdown(rep: dict) -> str:
    lines = ["# Two weeks of simulated operation", "", f"Database: {rep['database']}. Stand-in model. Clock fast-forwarded.", "",
             "| Day | Date | Jobs run | Failed (total) | Queue at night | Untriaged | Triaged twice | Drafts waiting | Log rows | Audit chain | Alerts raised | What happened |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in rep["days"]:
        ev = "; ".join(d["events"] + [f"{k.replace('_', ' ')}: {v}" for k, v in d["checks"].items()])
        lines.append(f"| {d['day']} | {d['weekday']} {d['date']} | {d['jobs_run']} | {d['failed_jobs_total']} | {d['queued_end_of_day']} | "
                     f"{d['mails_untriaged']} | {d['triaged_twice']} | {d['drafts_waiting']} | {sum(d['rows'].values())} | "
                     f"{'ok' if d['audit_chain_ok'] else 'BROKEN'} | "
                     f"{', '.join(f'{k} ({v})' for k, v in d.get('alerts', {}).items()) or 'none'} | {ev} |")
    return "\n".join(lines) + "\n"
