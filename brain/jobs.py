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

from .db import Job, Mail, Setting

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
}


def enqueue(s: Session, kind: str, payload: dict | None = None, run_after: datetime | None = None) -> Job:
    j = Job(kind=kind, payload=payload or {}, run_after=run_after or datetime.utcnow())
    s.add(j)
    s.flush()
    return j


def _handlers() -> dict[str, Callable[[Session, dict], dict]]:
    from .agents import change, followup, insight, partner_desk, proposal, supplier, trip_monitor, triage
    from .knowledge import vault

    def poll(s, p):
        ids = [m.id for m in s.scalars(select(Mail).where(Mail.status == "new")).all()]
        queued = {j.payload.get("mail_id") for j in s.scalars(select(Job).where(Job.kind == "triage_mail", Job.status == "queued")).all()}
        for i in ids:
            if i not in queued:
                enqueue(s, "triage_mail", {"mail_id": i})
        return {"queued": len([i for i in ids if i not in queued])}

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
    }


def is_paused(s: Session, kind: str) -> bool:
    agent = SCHEDULE.get(kind, (kind, None))[0]
    st = s.get(Setting, f"paused:{agent}")
    return bool(st and st.value)


def schedule_tick(s: Session, now: datetime | None = None) -> list[str]:
    """Queue periodic jobs whose interval has passed since their last run."""
    now = now or datetime.utcnow()
    added = []
    for kind, (_, minutes) in SCHEDULE.items():
        if not minutes:
            continue
        st = s.get(Setting, f"last_run:{kind}")
        last = datetime.fromisoformat(st.value) if st else None
        if last is None or now - last >= timedelta(minutes=minutes):
            enqueue(s, kind)
            s.merge(Setting(key=f"last_run:{kind}", value=now.isoformat()))
            added.append(kind)
    s.commit()
    return added


def work(s: Session, limit: int = 50) -> list[dict]:
    """Run due jobs, oldest first."""
    handlers = _handlers()
    done = []
    jobs = s.scalars(select(Job).where(Job.status == "queued", Job.run_after <= datetime.utcnow())
                     .order_by(Job.id).limit(limit)).all()
    for j in jobs:
        if is_paused(s, j.kind):
            continue
        j.status, j.attempts = "running", j.attempts + 1
        s.commit()
        try:
            res = handlers[j.kind](s, j.payload)
            j.status, j.result = "done", res if isinstance(res, dict) else {"result": str(res)[:500]}
        except Exception as e:  # noqa: BLE001
            s.rollback()
            j = s.get(Job, j.id)
            j.error = f"{type(e).__name__}: {e}"[:1000]
            if j.attempts >= MAX_ATTEMPTS or type(e).__name__ in ("BudgetExceeded", "ValueError", "KeyError"):
                j.status = "failed"
            else:
                j.status, j.run_after = "queued", datetime.utcnow() + timedelta(minutes=2 ** j.attempts)
        j.finished_at = datetime.utcnow()
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
