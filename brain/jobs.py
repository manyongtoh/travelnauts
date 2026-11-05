"""Work queue and scheduler.

Everything an agent does starts as a job in Postgres: a new mail, a request marked ready, the nightly
follow-ups. Workers pick up jobs, retry failures a few times, and skip jobs of a paused agent (they stay
queued until the agent is resumed). The scheduler adds the periodic jobs from SCHEDULE.

  brain worker            run the scheduler and the worker in a loop (Container Apps job in Azure)
  brain worker --once     one pass, for cron or tests
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import utcnow
from .db import Job, Mail, Setting

MAX_ATTEMPTS = 3
UPSTREAM = ("SystemUnavailable", "TravelSpiritUnavailable", "TimeoutError", "ConnectionError", "ConnectTimeout", "ReadTimeout")
UPSTREAM_PATIENCE = timedelta(hours=12)  # how long a job waits for TravelSpirit before it counts as failed

# kind -> (agent name for pausing, interval in minutes or None for event jobs)
SCHEDULE: dict[str, tuple[str, int | None]] = {
    "poll_inbox": ("triage", 5),
    "triage_mail": ("triage", None),
    "write_proposal": ("proposal_writer", None),
    "partner_reply": ("partner_desk", None),
    "chase_partners": ("partner_desk", 24 * 60),
    "followups": ("follow_up", 24 * 60),
    "supplier_watch": ("supplier_watcher", 24 * 60),
    "customer_insight": ("customer_insight", 24 * 60),
    "team_insight": ("team_insight", 60),
    "trip_monitor": ("trip_monitor", 60),
    "reindex_knowledge": ("knowledge_desk", 24 * 60),
    "knowledge_review_reminders": ("knowledge_desk", 24 * 60),
    "invoice": ("invoice_matcher", None),
    "complaint": ("complaints", None),
    "booking_check": ("booking_check", 24 * 60),
    "next_trips": ("next_trip", 7 * 24 * 60),
    "retention": ("maintenance", 24 * 60),
    "extras": ("extras", None),
    "alternatives": ("alternatives", None),
    "roadbook": ("roadbook", None),
    "alerts": ("maintenance", 15),
    "family_memory": ("maintenance", 24 * 60),
    "learning": ("maintenance", 24 * 60),
    "partner_scores": ("supplier_watcher", 24 * 60),
    "answer_question": ("knowledge_desk", None),
    "change": ("change", None),
}


def enqueue(s: Session, kind: str, payload: dict | None = None, run_after: datetime | None = None) -> Job:
    j = Job(kind=kind, payload=payload or {}, run_after=run_after or utcnow())
    s.add(j)
    s.flush()
    return j


def pending(s: Session, kind: str, request_id: str) -> bool:
    """Is a job of this kind for this request already waiting or running? Keeps triggers from piling up."""
    return any(j.payload.get("request_id") == request_id for j in
               s.scalars(select(Job).where(Job.kind == kind, Job.status.in_(["queued", "running"]))).all())


def auditchain_full(s: Session) -> bool:
    from .auditchain import verify_full_and_remember
    return verify_full_and_remember(s)["ok"]


def _answer_question(s: Session, mail_id: str) -> dict:
    """A family asked something: the knowledge desk drafts the answer for the specialist (or a blank to fill in)."""
    from .agents import knowledge_desk
    from .db import Draft
    m = s.get(Mail, mail_id)
    if any((d.data or {}).get("mail_id") == mail_id for d in s.scalars(select(Draft).where(Draft.kind == "answer")).all()):
        return {"skipped": "already drafted"}
    t = m.triage or {}
    res = knowledge_desk.ask(s, m.body[:1500], t.get("destination"), t.get("team_id"), mail_id=mail_id, role="specialist")
    return {"gap_id": res.get("gap_id"), "confident": res.get("confident")}


def _handlers() -> dict[str, Callable[[Session, dict], dict]]:
    from .agents import (
        backoffice,
        change,
        followup,
        insight,
        partner_desk,
        proposal,
        sales,
        supplier,
        triage,
        trip_monitor,
    )
    from .knowledge import vault

    def poll(s, p):
        ids = [m.id for m in s.scalars(select(Mail).where(Mail.status == "new")).all()]
        queued = {j.payload.get("mail_id") for j in s.scalars(select(Job).where(Job.kind == "triage_mail", Job.status == "queued")).all()}
        for i in ids:
            if i not in queued:
                enqueue(s, "triage_mail", {"mail_id": i})
        return {"queued": len([i for i in ids if i not in queued])}

    def next_trips(s, p):
        """Weekly: families back from a trip with us (two months or more) and nothing open get a next-trip idea,
        at most once a year and at most 5 a week."""
        from .alerts import OPEN_REQUEST_STATUSES
        from .clock import today as _today
        from .db import Draft, Family, TripRequest
        trips = s.scalars(select(TripRequest)).all()
        busy = {t.family_id for t in trips if t.status in OPEN_REQUEST_STATUSES
                or (t.status == "booked" and (t.depart_date is None or t.depart_date + timedelta(days=t.days) > _today()))}
        back = {t.family_id for t in trips if t.status == "booked" and t.depart_date
                and t.depart_date + timedelta(days=t.days + 60) <= _today()}
        year_ago = utcnow() - timedelta(days=365)
        done = {(d.data or {}).get("family_id") for d in s.scalars(select(Draft).where(
            Draft.kind == "next_trip", Draft.created_at >= year_ago)).all()}
        fams = [f for f in s.scalars(select(Family).order_by(Family.id)).all()
                if (f.past_destinations or f.id in back) and f.id not in busy and f.id not in done][:5]
        return {"drafted": len([sales.next_trip(s, f.id) for f in fams])}

    def chases(s, p):
        return {"drafted": len([partner_desk.draft_chase(s, pr.id) for pr in partner_desk.due_chases(s)])}

    return {
        "poll_inbox": poll,
        "triage_mail": lambda s, p: triage.triage_mail(s, p["mail_id"]),
        "write_proposal": lambda s, p: {"draft_id": proposal.write_proposal(s, p["request_id"]).id},
        "change": lambda s, p: {"draft_id": change.handle_change(s, p["mail_id"]).id},
        "partner_reply": lambda s, p: partner_desk.read_reply(s, p["mail_id"]),
        "chase_partners": chases,
        "followups": lambda s, p: {"withdrawn": __import__("brain.workflow", fromlist=["x"]).withdraw_stale_drafts(s),
                                   "drafted": len(followup.run_followups(s))},
        "supplier_watch": lambda s, p: supplier.watch(s),
        "customer_insight": lambda s, p: insight.customer_insight(s),
        "team_insight": lambda s, p: insight.team_insight(s),
        "trip_monitor": lambda s, p: trip_monitor.run(s),
        "reindex_knowledge": lambda s, p: vault.reindex(s),
        "knowledge_review_reminders": lambda s, p: vault.review_reminders(s),
        "invoice": lambda s, p: {"status": backoffice.invoices(s, p["mail_id"]).status},
        "complaint": lambda s, p: {"draft_id": sales.complaint(s, p["mail_id"]).id},
        "booking_check": lambda s, p: backoffice.booking_check(s),
        "next_trips": next_trips,
        "retention": lambda s, p: retention(s) | {"audit_full_check": auditchain_full(s)},
        "extras": lambda s, p: {"draft_id": sales.extras(s, p["request_id"]).id},
        "alternatives": lambda s, p: {"draft_id": sales.alternatives(s, p["request_id"]).id},
        "roadbook": lambda s, p: {"draft_id": backoffice.roadbook(s, p["request_id"]).id},
        "partner_scores": lambda s, p: __import__("brain.partner_scores", fromlist=["x"]).measure(s),
        "learning": lambda s, p: __import__("brain.learning", fromlist=["x"]).nightly(s),
        "answer_question": lambda s, p: _answer_question(s, p["mail_id"]),
        "family_memory": lambda s, p: {"ages_updated": __import__("brain.family", fromlist=["x"]).refresh_ages(s)},
        "alerts": lambda s, p: __import__("brain.alerts", fromlist=["notify"]).notify(s),
    }


def is_paused(s: Session, kind: str) -> bool:
    agent = SCHEDULE.get(kind, (kind, None))[0]
    st = s.get(Setting, f"paused:{agent}")
    return bool(st and st.value)


def _claim_setting(s: Session, key: str, old, new) -> bool:
    """Compare and set: only one scheduler wins when several run at once."""
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError
    if old is None:
        try:
            with s.begin_nested():
                s.add(Setting(key=key, value=new))
            return True
        except IntegrityError:
            return False
    import json

    from sqlalchemy import String, cast
    # Compare as text: works for JSON on Postgres and SQLite alike.
    res = s.execute(update(Setting).where(Setting.key == key, cast(Setting.value, String) == json.dumps(old)).values(value=new))
    return res.rowcount == 1


def schedule_tick(s: Session, now: datetime | None = None) -> list[str]:
    """Queue periodic jobs whose interval has passed since their last run. Safe with several schedulers."""
    now = now or utcnow()
    added = []
    for kind, (_, minutes) in SCHEDULE.items():
        if not minutes:
            continue
        st = s.get(Setting, f"last_run:{kind}")
        old = st.value if st else None
        last = datetime.fromisoformat(old) if old else None
        due = last is None or now - last >= timedelta(minutes=minutes)
        if due and _claim_setting(s, f"last_run:{kind}", old, now.isoformat()):  # one worker wins the claim
            enqueue(s, kind)
            added.append(kind)
    s.commit()
    return added


LEASE = timedelta(minutes=10)


def reap(s: Session) -> int:
    """Jobs whose worker died (lease ran out) go back in the queue."""
    from sqlalchemy import update
    res = s.execute(update(Job).where(Job.status == "running", Job.lease_until < utcnow())
                    .values(status="queued", worker=None, lease_until=None))
    s.commit()
    return res.rowcount


def claim(s: Session, worker: str, limit: int) -> list[int]:
    """Claim due jobs for this worker. Postgres skips rows another worker is claiming; the guarded update makes
    sure that a job is only ever claimed once, also on SQLite."""
    from sqlalchemy import update
    q = (select(Job.id).where(Job.status == "queued", Job.run_after <= utcnow()).order_by(Job.id).limit(limit))
    if s.get_bind().dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    ids = list(s.scalars(q).all())
    mine = []
    for jid in ids:
        kind = s.get(Job, jid).kind
        if is_paused(s, kind):
            continue
        res = s.execute(update(Job).where(Job.id == jid, Job.status == "queued")
                        .values(status="running", worker=worker, lease_until=utcnow() + LEASE, attempts=Job.attempts + 1))
        if res.rowcount == 1:
            mine.append(jid)
    s.commit()
    return mine


def work(s: Session, limit: int = 200, worker: str | None = None) -> list[dict]:
    """Claim and run due jobs, oldest first. Several workers can run this at the same time."""
    import os
    import socket
    handlers = _handlers()
    worker = worker or f"{socket.gethostname()}:{os.getpid()}"
    reap(s)
    done = []
    upstream_down = False
    for jid in claim(s, worker, limit):
        j = s.get(Job, jid)
        s.expire(j)
        if upstream_down:  # TravelSpirit just failed: do not hammer it, give the rest back to the queue
            j.status, j.attempts, j.worker, j.lease_until = "queued", max(j.attempts - 1, 0), None, None
            j.run_after = utcnow() + timedelta(minutes=5)
            s.commit()
            done.append({"id": j.id, "kind": j.kind, "status": "waiting", "error": j.error})
            continue
        from .toolserver import forget_failed_calls, keep_failed_calls
        forget_failed_calls()
        try:
            res = handlers[j.kind](s, j.payload)
            j = s.get(Job, jid)
            j.status, j.result = "done", res if isinstance(res, dict) else {"result": str(res)[:500]}
        except Exception as e:  # noqa: BLE001
            s.rollback()
            keep_failed_calls(s)
            j = s.get(Job, jid)
            j.error = f"{type(e).__name__}: {e}"[:1000]
            if type(e).__name__ in ("BudgetExceeded", "AgentPaused"):
                # Not the job's fault: wait and try again (every 15 minutes), without using up its attempts.
                j.status, j.attempts, j.run_after = "queued", max(j.attempts - 1, 0), utcnow() + timedelta(minutes=15)
                j.finished_at, j.worker, j.lease_until = utcnow(), worker, None
                s.commit()
                done.append({"id": j.id, "kind": j.kind, "status": "waiting", "error": j.error})
                continue
            if type(e).__name__ in UPSTREAM and utcnow() - j.created_at < UPSTREAM_PATIENCE:
                # TravelSpirit is down or slow: not the job's fault. Wait longer each time (5, 10, 20, 40, 60 minutes).
                waits = int((j.result or {}).get("upstream_waits", 0)) + 1
                j.status, j.attempts = "queued", max(j.attempts - 1, 0)
                j.run_after = utcnow() + timedelta(minutes=min(60, 5 * 2 ** (waits - 1)))
                j.result, j.error = {"upstream_waits": waits}, f"waiting for TravelSpirit: {e}"[:1000]
                j.finished_at, j.worker, j.lease_until = utcnow(), worker, None
                s.commit()
                upstream_down = True
                done.append({"id": j.id, "kind": j.kind, "status": "waiting", "error": j.error})
                continue
            permanent = type(e).__name__ in ("ValueError", "KeyError", "PrivacyError")
            if j.attempts >= MAX_ATTEMPTS or permanent:
                j.status = "failed"
            else:
                j.status, j.run_after = "queued", utcnow() + timedelta(minutes=2 ** j.attempts)
        j.finished_at, j.worker, j.lease_until = utcnow(), worker, None
        s.commit()
        done.append({"id": j.id, "kind": j.kind, "status": j.status, "error": j.error})
    return done


def loop(interval: int = 15) -> None:  # pragma: no cover - long running
    from . import db
    while True:
        with db.session() as s:
            schedule_tick(s)
            work(s)
            try:
                from . import autosend
                autosend.run_due(s)
            except Exception:  # never let a send problem stop the worker; drafts simply keep waiting
                s.rollback()
                import logging
                logging.getLogger("brain.autosend").exception("automatic send failed")
        time.sleep(interval)


def retention(s: Session, days: int = 30) -> dict:
    """Logs of prompts, tool calls and runs are kept 30 days (architecture: after PII masking, 30 days).
    The audit chain, drafts and approvals are not touched. Expired cache entries go too."""
    import os

    from .db import AgentRun, CacheEntry, ModelCall, ToolCall
    days = int(os.getenv("BRAIN_RETENTION_DAYS", days))
    cutoff = utcnow() - timedelta(days=days)
    out = {}
    for model in (ToolCall, ModelCall, AgentRun):
        out[model.__tablename__] = s.query(model).filter(model.created_at < cutoff).delete()
    out["cache"] = s.query(CacheEntry).filter(CacheEntry.expires_at < utcnow()).delete()
    out["jobs"] = s.query(Job).filter(Job.status == "done", Job.finished_at < cutoff).delete()
    s.commit()
    return out
