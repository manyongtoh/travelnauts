"""The runbook's morning check, done by the system every 15 minutes.

Each check returns an alert or nothing. New alerts and resolved alerts are posted once to a Teams (or any
JSON) webhook set in BRAIN_ALERT_WEBHOOK, and written to the log as "BRAIN_ALERT ..." so an Azure Monitor log
alert can page someone. Open alerts are shown at the top of the Maintenance screen.

Alerts carry no customer data: only counts, job kinds and ids.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import auditchain
from .tenant import tenant
from .clock import utcnow
from .db import AgentRun, Employee, Job, ModelCall, Setting, TripRequest

log = logging.getLogger("brain.alerts")

OPEN_KEY = "alerts:open"
CRITICAL, WARNING = "critical", "warning"
OPEN_REQUEST_STATUSES = ("new", "proposal_draft", "proposal_sent", "change_requested")  # as in team insight


@dataclass
class Alert:
    key: str          # stable id, so the same problem is reported once
    level: str        # critical: act now; warning: act today
    title: str
    detail: str
    action: str       # what to do, in the words of the runbook


def _setting(s: Session, key: str, default=None):
    st = s.get(Setting, key)
    return st.value if st else default


def checks(s: Session, now: datetime | None = None) -> list[Alert]:
    from .router import daily_cap, spent_today
    now = now or utcnow()
    out: list[Alert] = []

    chain = auditchain.verify_recent(s)  # new entries every 15 minutes; the whole log nightly (see retention)
    full = (s.get(Setting, "audit_full_check") or Setting(key="", value={})).value or {}
    if chain["ok"] and full and not full.get("ok", True):
        chain = full
    if not chain["ok"]:
        out.append(Alert("audit_chain", CRITICAL, "Audit chain broken",
                         f"Entry {chain['broken_at']} was changed or removed outside the application.",
                         "Do not repair. Export the database and tell the privacy contact today (runbook: audit chain)."))

    from .db import Draft
    on_road = [d for d in s.scalars(select(Draft).where(Draft.kind == "complaint_reply", Draft.status == "draft",
                                                        Draft.created_at < now - timedelta(minutes=30))).all()
               if (d.data or {}).get("while_travelling")]
    if on_road:
        out.append(Alert("travelling_family", CRITICAL, f"{len(on_road)} family message(s) from the road unanswered",
                         "A family that is travelling now wrote over 30 minutes ago and the reply is not sent. Requests: "
                         + ", ".join(sorted({d.request_id or "?" for d in on_road})),
                         "Team lead: open Complaints, call the family on the 24/7 line, send the reply."))

    failed = s.scalar(select(func.count()).select_from(Job).where(Job.status == "failed")) or 0
    if failed:
        kinds = sorted({k for (k,) in s.execute(select(Job.kind).where(Job.status == "failed").limit(50))})
        out.append(Alert("failed_jobs", CRITICAL if failed >= 5 else WARNING, f"{failed} failed job(s)",
                         "Kinds: " + ", ".join(kinds), "Find the cause in the job error, then Retry all failed in Maintenance."))

    waiting_ts = s.scalars(select(Job).where(Job.status == "queued", Job.error.like("waiting for TravelSpirit%"))).all()
    if waiting_ts:
        oldest = min(j.created_at for j in waiting_ts)
        level = CRITICAL if now - oldest > timedelta(hours=1) else WARNING
        out.append(Alert("travelspirit", level, "TravelSpirit is not answering",
                         f"{len(waiting_ts)} job(s) waiting since {oldest:%H:%M} UTC; they retry by themselves.",
                         "Check with the TravelSpirit administrator (runbook: TravelSpirit is unreachable)."))
    stuck = s.scalar(select(func.count()).select_from(Job).where(
        Job.status == "queued", Job.run_after < now - timedelta(minutes=30))) or 0
    if stuck:
        out.append(Alert("queue_behind", WARNING if stuck < 50 else CRITICAL, f"{stuck} job(s) waiting over 30 minutes",
                         "Workers are not keeping up, are stopped, or an agent is paused.",
                         "Check that workers run and no agent is paused by mistake (runbook: worker stops)."))

    last = _setting(s, "last_run:poll_inbox")
    if last and now - datetime.fromisoformat(last) > timedelta(minutes=30):
        out.append(Alert("scheduler", CRITICAL, "Scheduler has stopped",
                         f"No inbox poll since {last[:16]} UTC.", "Restart the worker container app."))

    cap, spent = daily_cap(s), spent_today(s)
    if cap is not None and spent >= cap:  # a cap of 0 means: spend nothing, so it counts as reached
        out.append(Alert("budget", CRITICAL, "Daily model budget reached", f"EUR {spent:.2f} of {cap:.2f}; jobs are waiting.",
                         "Decide with the GM: raise today's budget or wait until tomorrow (runbook: budget)."))
    elif cap and spent >= 0.8 * cap:
        out.append(Alert("budget", WARNING, "Model budget at 80%", f"EUR {spent:.2f} of {cap:.2f}.",
                         "Look for a mail loop or an unusual peak."))

    hour = now - timedelta(hours=1)
    calls = s.scalars(select(ModelCall).where(ModelCall.created_at >= hour)).all()
    if len(calls) >= 5 and sum(not c.ok for c in calls) / len(calls) > 0.2:
        out.append(Alert("model_errors", WARNING, "Model errors above 20% in the last hour",
                         f"{sum(not c.ok for c in calls)} of {len(calls)} calls failed; "
                         f"{sum(c.fallback_from is not None for c in calls)} used the fallback.",
                         "Check the provider status page (runbook: model provider down)."))

    # Agent failures of their own: waits for budget or a pause, and failures already explained by a model
    # outage, are not the agent's fault and would only repeat another alert.
    per: dict[str, list[int]] = {}
    for agent, ok, error in s.execute(select(AgentRun.agent, AgentRun.ok, AgentRun.error).where(AgentRun.created_at >= hour)):
        if error and (error.split(":")[0] in ("BudgetExceeded", "AgentPaused", "TravelSpiritUnavailable", "TimeoutError")
                      or "All models failed" in error):
            continue
        per.setdefault(agent, [0, 0])
        per[agent][0] += 1
        per[agent][1] += not ok
    bad = [a for a, (n, err) in per.items() if n >= 5 and err / n > 0.3]
    if bad and not any(a.key == "model_errors" for a in out):
        out.append(Alert("agent_errors", WARNING, "Agent failing often", "Over 30% failed in the last hour: " + ", ".join(sorted(bad)),
                         "Pause the agent if its drafts are wrong (runbook: agent does something wrong)."))

    ownerless = s.scalar(select(func.count()).select_from(TripRequest).join(Employee, TripRequest.specialist_id == Employee.id)
                         .where(Employee.active.is_(False), TripRequest.status.in_(OPEN_REQUEST_STATUSES))) or 0
    if ownerless:
        out.append(Alert("ownerless", WARNING, f"{ownerless} open request(s) without an owner",
                         "Their specialist is no longer active.", "Reassign them in Team lead > Insight."))
    return out


def _allowed(url: str) -> bool:
    """Only https, or plain http to this machine (tests). Never file: or other schemes."""
    from urllib.parse import urlparse
    u = urlparse(url)
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost"))


def _post(url: str, text: str) -> bool:
    if not _allowed(url):
        log.warning("BRAIN_ALERT_DELIVERY_FAILED webhook must be an https address")
        return False
    body = json.dumps({"text": text}).encode()
    # bandit B310: the scheme is checked in _allowed above
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:  # nosec B310
            return 200 <= r.status < 300
    except Exception as e:  # noqa: BLE001  an alert channel being down must never stop the brain
        log.warning("BRAIN_ALERT_DELIVERY_FAILED %s", type(e).__name__)
        return False


def notify(s: Session, now: datetime | None = None) -> dict:
    """Report alerts that are new or got worse, and alerts that cleared. Called by the scheduler."""
    current = {a.key: a for a in checks(s, now)}
    log.warning("BRAIN_ALERT_HEARTBEAT open=%d", len(current))  # Azure pages someone if this stops
    before: dict = _setting(s, OPEN_KEY, {}) or {}
    new = [a for k, a in current.items() if k not in before or before[k] != a.level]
    cleared = [k for k in before if k not in current]
    env = os.getenv("BRAIN_ENV", "test")
    lines = [f"[{a.level.upper()}] {a.title}: {a.detail} Action: {a.action}" for a in new]
    lines += [f"[RESOLVED] {k}" for k in cleared]
    for line in lines:
        (log.error if "CRITICAL" in line else log.warning)("BRAIN_ALERT env=%s %s", env, line)
    url = os.getenv("BRAIN_ALERT_WEBHOOK")
    delivered = _post(url, f"{tenant().short_name} brain ({env})\n\n" + "\n\n".join(lines)) if (url and lines) else None
    st = s.get(Setting, OPEN_KEY)
    value = {k: a.level for k, a in current.items()}
    if st:
        st.value = value
    else:
        s.add(Setting(key=OPEN_KEY, value=value))
    s.commit()
    return {"open": len(current), "new": len(new), "cleared": len(cleared), "delivered": delivered}


def as_json(alerts: list[Alert]) -> list[dict]:
    order = {CRITICAL: 0, WARNING: 1}
    return [asdict(a) for a in sorted(alerts, key=lambda a: order[a.level])]
