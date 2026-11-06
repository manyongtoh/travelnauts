from datetime import date, timedelta

import pytest
from sqlalchemy import select

from brain import db
from brain.agents import (
    followup,
    gds,
    knowledge_desk,
    partner_desk,
    proposal,
    triage,
)
from brain.config import Settings
from brain.db import (
    Draft,
    Family,
    KnowledgeItem,
    Mail,
    PartnerRequest,
    PriceItem,
    TripRequest,
)
from brain.knowledge.store import KnowledgeBase
from brain.workflow import approve_draft, edit_share


def test_live_data_is_refused():
    with pytest.raises(RuntimeError):
        Settings(data_stage="live").check()


def test_agents_cannot_write_final_records():
    with pytest.raises(ValueError):
        Settings(travelspirit_write="full").check()


def test_real_rows_are_refused_in_synthetic_stage(world):
    world.add(Family(id="real1", surname="X", contact_name="X", email="x@x", adults=2, child_ages=[], city="X",
                     synthetic=False))
    world.commit()
    with pytest.raises(RuntimeError):
        db.assert_synthetic_only(world)


def test_triage_routes_new_requests_to_the_right_team(world):
    results = triage.triage_inbox(world)
    mails = {m.id: m for m in world.scalars(select(Mail)).all()}
    new = [m for m in mails.values() if m.truth["category"] == "new_request"]
    assert new and all(m.triage["team_id"] == m.truth["team"] for m in new)
    assert all(world.get(TripRequest, m.triage["request_id"]).specialist_id for m in new)
    assert len(results) == len(mails)


def test_proposal_uses_only_approved_knowledge_and_safe_activities(world):
    triage.triage_inbox(world)
    req = world.scalars(select(TripRequest).where(TripRequest.mail_id.is_not(None))).first()
    d = proposal.write_proposal(world, req.id)
    approved = {k.id for k in world.scalars(select(KnowledgeItem).where(KnowledgeItem.status == "approved")).all()}
    cited = [x["id"] for x in d.sources if x["type"] == "knowledge"]
    assert cited and set(cited) <= approved
    fam = world.get(Family, req.family_id)
    for stop in d.data["route"]:
        for a in stop["activities"]:
            item = world.scalars(select(PriceItem).where(PriceItem.name == a)).first()
            assert item.min_child_age <= min(fam.child_ages)
    assert sum(r["nights"] for r in d.data["route"]) == req.days - 2
    assert d.data["price"]["sell_eur"] > d.data["price"]["cost_eur"]
    assert d.status == "draft"


def test_unapproved_knowledge_is_invisible_until_approved(world):
    kb = KnowledgeBase(world)
    kb.propose("k-test", "Kinderwagen in Thailand", "In Bangkok is een draagzak handiger dan een kinderwagen.",
               "sanne-de-vries", "thailand", "family", date.today() + timedelta(days=90))
    assert all(h.id != "k-test" for h in kb.search("kinderwagen Thailand"))
    kb.approve("k-test", "Marloes Kuiper")
    assert kb.search("kinderwagen Thailand")[0].id == "k-test"


def test_unknown_question_becomes_a_gap(world):
    res = knowledge_desk.ask(world, "Kun je in Sri Lanka goed glutenvrij eten?")
    assert res["confident"] is False and res["gap_id"]
    res2 = knowledge_desk.ask(world, "Kun je in Sri Lanka goed glutenvrij eten?")
    assert res2["gap_id"] == res["gap_id"]
    assert KnowledgeBase(world).gaps()[0].count == 2


def test_known_question_is_answered_with_its_source(world):
    res = knowledge_desk.ask(world, "Wat is de beste reistijd voor Japan?")
    assert res["confident"] and res["cited"] == ["k-japan-season"]


def test_heavy_rewrite_is_measured_and_becomes_a_gap(world):
    triage.triage_inbox(world)
    req = world.scalars(select(TripRequest).where(TripRequest.mail_id.is_not(None))).first()
    d = proposal.write_proposal(world, req.id)
    approve_draft(world, d.id, "Sanne de Vries", "Helemaal ander verhaal, kort en zakelijk.")
    assert d.edit_share > 0.5
    assert world.get(TripRequest, req.id).status == "proposal_sent"
    assert any(g.reason == "heavy_rewrite" for g in KnowledgeBase(world).gaps())
    assert edit_share("abc", "abc") == 0


def test_partner_desk_flow(world):
    triage.triage_inbox(world)
    req = world.scalars(select(TripRequest).where(TripRequest.mail_id.is_not(None))).first()
    d = proposal.write_proposal(world, req.id)
    created = partner_desk.plan_partner_requests(world, req.id)
    assert len(created) == 1 + len(d.data["route"])
    mails = world.scalars(select(Draft).where(Draft.kind == "partner_request", Draft.request_id == req.id)).all()
    assert len(mails) == len(created)
    fam = world.get(Family, req.family_id)
    assert all(fam.contact_name not in m.body for m in mails)  # no customer names to partners
    for m in mails:
        approve_draft(world, m.id, "Ruben Stam")
    assert all(world.get(PartnerRequest, p.id).status == "waiting" for p in created)
    assert partner_desk.plan_partner_requests(world, req.id) == []  # no duplicates


def test_booking_commands_pass_the_format_check(world):
    triage.triage_inbox(world)
    req = world.scalars(select(TripRequest).where(TripRequest.mail_id.is_not(None))).first()
    g = gds.write_commands(world, req.id)
    assert g.data["commands"] and not [w for w in g.data["warnings"] if "onbekend formaat" in w]
    assert not any(c["cmd"] in ("E", "ER", "TKP") for c in g.data["commands"])  # never ends or tickets


def test_followups_only_once(world):
    first = followup.run_followups(world)
    assert first
    assert followup.run_followups(world) == []


def test_every_run_is_logged(world):
    from brain.db import AgentRun
    knowledge_desk.ask(world, "Wat is de beste reistijd voor Japan?")
    run = world.scalars(select(AgentRun).order_by(AgentRun.id.desc())).first()
    assert run.agent == "knowledge_desk" and run.sources and run.ok
