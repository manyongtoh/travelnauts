"""The core under stress: failing models, parallel workers, failed agents, privacy at the model boundary."""
import multiprocessing as mp
import os

import pytest
from sqlalchemy import select, text

from brain import auditchain, jobs
from brain.agents import knowledge_desk, proposal, triage
from brain.db import AgentRun, AuditEntry, Job, Mail, ModelCall, Quote, TripRequest
from brain.guardrails import PrivacyError, Pseudonymiser


def test_children_names_never_reach_the_model():
    p = Pseudonymiser()
    m = p.mask({"family": {"name": "Anouk de Wit"},
                "mail": {"body": "Hallo,\n\nWij willen met Floor (8) en Sem (12) naar Japan. Mijn man Pieter belt.\n\nGroet,\nAnouk de Wit"}})
    for name in ("Floor", "Sem", "Pieter", "Anouk", "Wit"):
        assert name not in str(m)
    assert "Floor (8)" in p.unmask(m)["mail"]["body"]


def test_model_call_refused_if_a_known_name_slips_through():
    p = Pseudonymiser()
    p.forward["Femke"] = "[NAAM_1]"
    with pytest.raises(PrivacyError):
        p.check({"mail": {"body": "Hallo Femke, dit is een lange tekst over de reis naar Japan in april met de kinderen.\n"}})


def test_garbage_output_is_retried_until_valid(world, monkeypatch):
    monkeypatch.setenv("BRAIN_MODEL_SMALL", "test:garbage")
    res = knowledge_desk.ask(world, "Wat is de beste reistijd voor Japan?")
    assert res["confident"]


def test_timeouts_fall_back_and_a_failing_model_is_skipped(world, monkeypatch):
    monkeypatch.setenv("BRAIN_MODEL_SMALL", "test:slow")
    monkeypatch.setenv("BRAIN_MODEL_FALLBACK", "sandbox")
    for q in ["Japan", "Thailand", "Vietnam", "Costa Rica", "Tanzania", "Sri Lanka"]:  # different questions: no cache
        knowledge_desk.ask(world, f"Wat is de beste reistijd voor {q}?")
    slow = world.scalars(select(ModelCall).where(ModelCall.model == "test:slow")).all()
    assert 5 <= len(slow) < 6  # after five failures the circuit opens and the slow model is skipped


def test_failed_agent_leaves_nothing_half_done(world, monkeypatch):
    triage.triage_inbox(world)
    tr = world.scalars(select(TripRequest).where(TripRequest.mail_id.is_not(None))).first()
    quotes_before = world.query(Quote).count()
    monkeypatch.setenv("BRAIN_MODEL_LARGE", "test:broken")
    with pytest.raises(RuntimeError):
        proposal.write_proposal(world, tr.id)
    assert world.query(Quote).count() == quotes_before  # the quote made before the failure is rolled back
    assert world.get(TripRequest, tr.id).status == "new"
    run = world.scalars(select(AgentRun).order_by(AgentRun.id.desc())).first()
    assert run.agent == "proposal_writer" and not run.ok
    assert world.scalars(select(ModelCall).where(ModelCall.model == "test:broken")).all()  # cost record kept


def test_jobs_are_safe_to_repeat(world):
    triage.triage_inbox(world)
    m = world.scalars(select(Mail).where(Mail.status == "triaged")).first()
    runs = world.query(AgentRun).filter(AgentRun.agent == "triage").count()
    assert triage.triage_mail(world, m.id)["skipped"]
    assert world.query(AgentRun).filter(AgentRun.agent == "triage").count() == runs


def test_a_job_is_claimed_by_one_worker_only(world):
    j = jobs.enqueue(world, "poll_inbox")
    world.commit()
    first = jobs.claim(world, "w1", 10)
    second = jobs.claim(world, "w2", 10)
    assert j.id in first and j.id not in second


def test_dead_workers_jobs_come_back(world):
    from datetime import timedelta
    from brain.clock import utcnow
    j = jobs.enqueue(world, "poll_inbox")
    world.commit()
    jobs.claim(world, "w1", 10)
    world.get(Job, j.id).lease_until = utcnow() - timedelta(minutes=1)
    world.commit()
    assert jobs.reap(world) == 1 and world.get(Job, j.id).status == "queued"


def test_two_schedulers_queue_each_job_once(world):
    jobs.schedule_tick(world)
    jobs.schedule_tick(world)
    kinds = [j.kind for j in world.scalars(select(Job)).all()]
    assert kinds.count("followups") == 1


def test_scheduler_runs_again_after_the_interval(world):
    from datetime import timedelta
    from brain.clock import utcnow
    jobs.schedule_tick(world, utcnow())
    later = jobs.schedule_tick(world, utcnow() + timedelta(hours=2))  # the compare and set path, not the first insert
    assert "trip_monitor" in later and "followups" not in later
    assert jobs.schedule_tick(world, utcnow() + timedelta(hours=2)) == []


def test_audit_chain_cannot_fork(world):
    a = auditchain.append(world, "a", "approve", "draft", 1)
    world.commit()
    fork = AuditEntry(at=a.at, actor="b", action="approve", object_type="draft", object_id="2", prev_hash=a.prev_hash, hash="x")
    world.add(fork)
    with pytest.raises(Exception):
        world.commit()
    world.rollback()
    assert auditchain.verify(world)["ok"]


def test_request_numbers_stay_unique(world):
    from brain.db import next_number
    nums = [next_number(world, "request", start_from=30) for _ in range(20)]
    assert len(set(nums)) == 20 and nums[0] == 31


def _parallel_worker(url, name):
    os.environ["BRAIN_DATABASE_URL"] = url
    from brain import db, jobs as j
    db.reset_engine(url)
    n = 0
    with db.session() as s:
        for _ in range(30):
            done = j.work(s, limit=10, worker=name)
            n += len(done)
            if not done:
                break
    return n


def test_parallel_workers_never_double_process(tmp_path):
    from brain import db
    from brain.synth.generate import build
    url = os.getenv("BRAIN_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'par.db'}"
    os.environ["BRAIN_VAULT"] = str(tmp_path / "vault")
    os.environ["BRAIN_FILES"] = str(tmp_path / "files")
    db.reset_engine(url)
    build(seed=11, n_families=60, hard=False)
    with db.session() as s:
        jobs.enqueue(s, "poll_inbox")
        s.commit()
    with mp.get_context("spawn").Pool(3) as pool:
        pool.starmap(_parallel_worker, [(url, f"w{i}") for i in range(3)])
    db.reset_engine(url)
    with db.session() as s:
        triaged = [r.subject for r in s.scalars(select(AgentRun).where(AgentRun.agent == "triage")).all()]
        assert len(triaged) == len(set(triaged)) and s.query(Mail).filter(Mail.status == "new").count() == 0
        left = [(j.kind, j.status, (j.error or "")[:80]) for j in s.scalars(select(Job)).all() if j.status != "done"]
        assert not left, left
    db.reset_engine()


def test_an_edited_note_keeps_its_approved_text_until_the_change_is_approved(world):
    from brain.db import KnowledgeItem
    from brain.knowledge import vault
    from brain.knowledge.store import KnowledgeBase
    item = world.get(KnowledgeItem, "k-japan-season")
    old = item.body
    note = vault.vault_dir() / item.source
    note.write_text(note.read_text().replace(old, old + " Let op: de kersenbloesem valt eind maart."))
    vault.reindex(world)
    world.refresh(item)
    assert item.status == "approved" and item.body == old and "kersenbloesem" in item.pending_body
    assert KnowledgeBase(world).search("beste reistijd japan", k=1)[0].body == old
    KnowledgeBase(world).approve("k-japan-season", "Marloes Kuiper")
    assert "kersenbloesem" in KnowledgeBase(world).search("beste reistijd japan", k=1)[0].body
    vault.reindex(world)
    assert world.get(KnowledgeItem, "k-japan-season").pending_body is None


def test_verify_reports_counts_and_catches_a_changed_audit_entry(world):
    from sqlalchemy import update
    from brain.db import AuditEntry
    from brain.ops_verify import verify_database
    for i in range(3):
        auditchain.append(world, "test", "approve", "draft", f"d{i}")
    world.commit()
    r = verify_database()
    assert r["ok"] and r["rows"]["requests"] > 0 and r["audit_chain"]["entries"] == 3
    first = world.scalars(select(AuditEntry).order_by(AuditEntry.id)).first()
    world.execute(update(AuditEntry).where(AuditEntry.id == first.id).values(actor="someone-else"))
    world.commit()
    r = verify_database()
    assert not r["ok"] and "audit chain broken" in r["problems"][0]


def test_migrate_adopts_a_matching_database_and_refuses_a_different_one(world, tmp_path):
    import pytest as _pt
    from alembic.config import Config
    from brain.config import ROOT
    from brain.ops_verify import adopt_unmanaged
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    if world.bind.dialect.name != "sqlite":
        _pt.skip("schema surgery below is written for SQLite")
    assert "newest migration" in adopt_unmanaged(cfg)
    assert adopt_unmanaged(cfg) is None  # already managed: nothing to do
    world.execute(text("drop table alembic_version"))
    world.execute(text("alter table knowledge drop column pending_hash"))
    world.commit()
    with _pt.raises(SystemExit, match="differs from the code"):
        adopt_unmanaged(cfg)
