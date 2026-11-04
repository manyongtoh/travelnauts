"""Load and concurrency test: many mails, several workers at the same time.

  brain loadtest --mails 600 --workers 4      (use Postgres: BRAIN_DATABASE_URL=postgresql+psycopg://...)

Checks that with parallel workers every mail is triaged exactly once, no job runs twice, request numbers
stay unique, approvals from several people at once keep the audit chain intact, and reports throughput.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import random
import time
from collections import Counter

from sqlalchemy import func, select


def _extra_mails(n: int, seed: int) -> None:
    from .. import db
    from ..db import Family, Mail
    from ..synth.world import DESTINATIONS
    rng = random.Random(seed)
    with db.session() as s:
        fams = list(s.scalars(select(Family)).all())
        months = ["januari", "maart", "april", "mei", "juli", "augustus", "oktober", "december"]
        for i in range(n):
            f = rng.choice(fams)
            dest = rng.choice(list(DESTINATIONS))
            days = rng.choice([14, 18, 21])
            ages = " en ".join(str(a) for a in f.child_ages)
            s.add(Mail(id=f"load{i:05d}", received_at=db.now(), sender=f.email, subject=f"Aanvraag {DESTINATIONS[dest]['nl']}",
                       body=f"Hallo,\n\nWij willen graag in {rng.choice(months)} naar {DESTINATIONS[dest]['nl']}, {days} dagen.\n"
                            f"We zijn met {f.adults} volwassenen en {len(f.child_ages)} kinderen ({ages} jaar).\n\nGroet, {f.contact_name}",
                       family_id=f.id, truth={"category": "new_request", "set": "load"}))
        s.commit()


def _worker(url: str, name: str, until: float) -> int:
    os.environ["BRAIN_DATABASE_URL"] = url
    from .. import db, jobs
    db.reset_engine(url)
    n = 0
    idle = 0
    with db.session() as s:
        while time.time() < until and idle < 3:
            done = jobs.work(s, limit=20, worker=name)
            n += len(done)
            idle = idle + 1 if not done else 0
            if not done:
                time.sleep(0.5)
    return n


def _approver(url: str, ids: list[int], who: str) -> int:
    os.environ["BRAIN_DATABASE_URL"] = url
    from .. import db
    from ..workflow import approve_draft
    db.reset_engine(url)
    ok = 0
    with db.session() as s:
        for d in ids:
            try:
                approve_draft(s, d, who, actor_id=who)
                ok += 1
            except Exception:  # noqa: BLE001
                s.rollback()
    return ok


def run(mails: int = 600, workers: int = 4, seed: int = 42, timeout: int = 900) -> dict:
    from .. import auditchain, db, jobs
    from ..db import AgentRun, Draft, Job, Mail, TripRequest
    from ..synth.generate import build
    url = os.environ.get("BRAIN_DATABASE_URL", "")
    build(seed, hard=False)
    _extra_mails(mails, seed)
    with db.session() as s:
        jobs.enqueue(s, "poll_inbox")
        s.commit()
        total_mails = s.query(Mail).filter(Mail.status == "new").count()
    ctx = mp.get_context("spawn")
    t0 = time.time()
    with ctx.Pool(workers) as pool:
        counts = pool.starmap(_worker, [(url, f"w{i}", t0 + timeout) for i in range(workers)])
    secs = time.time() - t0
    with db.session() as s:
        triage_runs = Counter(r.subject for r in s.scalars(select(AgentRun).where(AgentRun.agent == "triage")).all())
        jobs_by_status = dict(Counter(j.status for j in s.scalars(select(Job)).all()))
        dup_jobs = s.scalar(select(func.count()).select_from(Job).where(Job.kind == "triage_mail")) - len(
            {j.payload.get("mail_id") for j in s.scalars(select(Job).where(Job.kind == "triage_mail")).all()})
        untriaged = s.query(Mail).filter(Mail.status == "new").count()
        reqs = s.query(TripRequest).count()
        # Now several people approve drafts at the same moment: the audit chain must stay one line.
        from ..agents import proposal
        sample = [t.id for t in s.scalars(select(TripRequest).where(TripRequest.mail_id.is_not(None)).limit(workers * 5)).all()]
        drafts = [proposal.write_proposal(s, r).id for r in sample]
    chunks = [drafts[i::workers] for i in range(workers)]
    with ctx.Pool(workers) as pool:
        approved = sum(pool.starmap(_approver, [(url, c, f"user{i}") for i, c in enumerate(chunks)]))
    with db.session() as s:
        chain = auditchain.verify(s)
        per_worker = dict(Counter(j.worker.split(":")[0] if j.worker else "-" for j in s.scalars(select(Job)).all()))
    return {
        "database": url.split("@")[-1] if "@" in url else url.split("///")[-1],
        "workers": workers, "mails": total_mails, "seconds": round(secs, 1),
        "mails_per_minute": round(total_mails / secs * 60) if secs else None,
        "jobs": jobs_by_status, "jobs_per_worker": per_worker,
        "mails_triaged_more_than_once": sum(1 for v in triage_runs.values() if v > 1),
        "duplicate_triage_jobs": dup_jobs, "mails_left_untriaged": untriaged, "requests": reqs,
        "concurrent_approvals": approved, "audit_chain": chain,
    }
