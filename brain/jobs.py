"""Work queue and scheduler.

Everything an agent does starts as a job in Postgres: a new mail, a request marked ready, the nightly
follow-ups. Workers pick up jobs, retry failures a few times, and skip jobs of a paused agent (they stay
queued until the agent is resumed). The scheduler adds the periodic jobs from SCHEDULE.

  brain worker            run the scheduler and the worker in a loop (Container Apps job in Azure)
  brain worker --once     one pass, for cron or tests
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import utcnow
from .db import Job, Mail, Setting
from .clock import utcnow

MAX_ATTEMPTS = 3

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
}


def enqueue(s: Session, kind: str, payload: dict | None = None, run_after: datetime | None = None) -> Job:
    j = Job(kind=kind, payload=payload or {}, run_after=run_after or utcnow())
    s.add(j)
    s.flush()
    return j


def _handlers() -> dict[str, Callable[[Session, dict], dict]]:
    from .agents import backoffice, change, followup, insight, partner_desk, proposal, sales, supplier, trip_monitor, triage
    from .knowledge import vault

    def poll(s, p):
        ids = [m.id for m in s.scalars(select(Mail).where(Mail.status == "new")).all()]
        queued = {j.payload.get("mail_id") for j in s.scalars(select(Job).where(Job.kind == "triage_mail", Job.status == "queued")).all()}
        for i in ids:
            if i not in queued:
                enqueue(s, "triage_mail", {"mail_id": i})
        return {"queued": len([i for i in ids if i not in queued])}

    def next_trips(s, p):
        """Weekly: families who travelled with us and have nothing open get a next-trip idea (max 5 a week)."""
        from .db import Draft, Family, TripRequest
        open_fams = {t.family_id for t in s.scalars(select(TripRequest)).all() if t.status != "lost"}
        done = {(d.data or {}).get("family_id") for d in s.scalars(select(Draft).where(Draft.kind == "next_trip")).all()}
        fams = [f for f in s.scalars(select(Family).where(Family.synthetic.is_(True))).all()
                if f.past_destinations and f.id not in open_fams and f.id not in done][:5]
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
        "followups": lambda s, p: {"drafted": len(followup.run_followups(s))},
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
        "retention": lambda s, p: retention(s),
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
    res = s.execute(update(Setting).where(Setting.key == key, Setting.value == old).values(value=new))
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
        if last is None or now - last >= timedelta(minutes=minutes):
            if _claim_setting(s, f"last_run:{kind}", old, now.isoformat()):
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
    for jid in claim(s, worker, limit):
        j = s.get(Job, jid)
        s.expire(j)
        try:
            res = handlers[j.kind](s, j.payload)
            j = s.get(Job, jid)
            j.status, j.result = "done", res if isinstance(res, dict) else {"result": str(res)[:500]}
        except Exception as e:  # noqa: BLE001
            s.rollback()
            j = s.get(Job, jid)
            j.error = f"{type(e).__name__}: {e}"[:1000]
            permanent = type(e).__name__ in ("BudgetExceeded", "ValueError", "KeyError", "PrivacyError", "AgentPaused")
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
        time.sleep(interval)


def retention(s: Session, days: int = 30) -> dict:
    """Logs of prompts, tool calls and runs are kept 30 days (architecture: after PII masking, 30 days).
    The audit chain, drafts and approvals are not touched. Expired cache entries go too."""
    from .db import AgentRun, CacheEntry, ModelCall, ToolCall
    cutoff = utcnow() - timedelta(days=days)
    out = {}
    for model in (ToolCall, ModelCall, AgentRun):
        out[model.__tablename__] = s.query(model).filter(model.created_at < cutoff).delete()
    out["cache"] = s.query(CacheEntry).filter(CacheEntry.expires_at < utcnow()).delete()
    out["jobs"] = s.query(Job).filter(Job.status == "done", Job.finished_at < cutoff).delete()
    s.commit()
    return out
