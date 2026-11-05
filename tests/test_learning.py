"""The brain learns from daily work: edits, outcomes, answers, ages, expertise, partners and search.
Nothing it learns is used before a person approves it."""
from datetime import timedelta

from sqlalchemy import select

from brain import clock, jobs, learning
from brain.agents import proposal, triage
from brain.db import Draft, Employee, Family, KnowledgeGap, KnowledgeItem, Mail, Partner, PartnerRequest, PastProposal, TripRequest
from brain.knowledge.store import KnowledgeBase
from brain.workflow import BlockedByCheck, approve_draft

RULE = "Autostoeltjes voor de kinderen regelen we met de huurauto mee."


def new_requests(s, n, team=None):
    q = select(TripRequest).where(TripRequest.status == "new").order_by(TripRequest.id)
    if team:
        q = q.where(TripRequest.team_id == team)
    return s.scalars(q).all()[:n]


def team_with_new_requests(s, n=3):
    from collections import Counter
    c = Counter(t.team_id for t in s.scalars(select(TripRequest).where(TripRequest.status == "new")).all())
    return next(t for t, k in c.most_common() if k >= n)


# 1. house rules from edits ---------------------------------------------------------------------------------------

def test_what_specialists_keep_adding_becomes_a_proposed_house_rule(world):
    team = team_with_new_requests(world)
    people = world.scalars(select(Employee).where(Employee.role == "specialist", Employee.team_id == team)).all()
    for i, tr in enumerate(new_requests(world, 3, team)):
        d = proposal.write_proposal(world, tr.id)
        approve_draft(world, d.id, people[i % 2].name, d.body + "\n\n" + RULE)
    out = learning.learn_from_edits(world)
    assert out["house_rules_proposed"] == 1
    rule = world.scalars(select(KnowledgeItem).where(KnowledgeItem.topic == "house_rule")).one()
    from brain.knowledge import vault
    vault.reindex(world)  # the nightly vault read must not retire what was learned
    world.refresh(rule)
    assert rule.status == "proposed" and "Autostoeltjes" in rule.body and f"team:{team}" in rule.tags
    assert learning.house_rules(world, team, "proposal") == []  # not used before approval
    KnowledgeBase(world).approve(rule.id, "team lead")
    assert learning.house_rules(world, team, "proposal") == [rule.body]
    assert learning.learn_from_edits(world)["house_rules_proposed"] == 0  # proposed once, also when turned down
    assert rule.id not in [h.id for h in KnowledgeBase(world).search("autostoeltjes huurauto", k=5)]  # rules stay out of search


def test_one_specialists_habit_or_a_personal_line_is_not_a_rule(world):
    team = team_with_new_requests(world)
    spec = world.scalars(select(Employee).where(Employee.role == "specialist", Employee.team_id == team)).first()
    for tr in new_requests(world, 3, team):
        fam = world.get(Family, tr.family_id)
        d = proposal.write_proposal(world, tr.id)
        approve_draft(world, d.id, spec.name, d.body + f"\n\n{RULE}\nGroetjes aan {fam.contact_name.split()[0]} en de kinderen!")
    assert learning.learn_from_edits(world)["house_rules_proposed"] == 0  # one person only, and the other line is personal


# 2. examples from outcomes ---------------------------------------------------------------------------------------

def test_a_booked_proposal_becomes_an_example_without_names_and_is_preferred(world):
    tr = new_requests(world, 1)[0]
    fam = world.get(Family, tr.family_id)
    d = proposal.write_proposal(world, tr.id)
    approve_draft(world, d.id, "spec")
    tr.status = "booked"
    world.commit()
    assert learning.learn_from_outcomes(world)["examples_added"] >= 1
    ex = world.get(PastProposal, f"learned-{d.id}")
    assert ex.booked and ex.source_draft_id == d.id and all(r.get("hotel") for r in ex.route)
    for part in fam.contact_name.split() + [fam.surname]:
        if len(part) > 2:
            assert part not in ex.text
    from brain.learning import rank_examples
    rows = list(world.scalars(select(PastProposal).where(PastProposal.destination == tr.destination)).all())
    best = rank_examples(rows, tr.days, fam.child_ages, k=1)[0]
    assert best.booked
    tr.status = "lost"
    world.commit()
    assert learning.learn_from_outcomes(world)["examples_updated"] == 1 and not world.get(PastProposal, f"learned-{d.id}").booked


# 3. family memory --------------------------------------------------------------------------------------------------

def test_childrens_ages_count_up(world):
    from brain.family import refresh_ages
    fam = next(f for f in world.scalars(select(Family)).all() if f.child_ages)
    before = list(fam.child_ages)
    assert fam.child_birth_years
    try:
        clock.set_now(clock.utcnow() + timedelta(days=2 * 366))
        refresh_ages(world)
        assert world.get(Family, fam.id).child_ages == [a + 2 for a in before]
    finally:
        clock.reset()


def test_agents_see_the_familys_history(world):
    from brain.toolserver import server
    from brain.identity import agent
    tr = world.scalars(select(TripRequest).where(TripRequest.status == "booked")).first()
    rel = server.call(world, agent("proposal_writer"), "ts.read_relation", family_id=tr.family_id)
    assert tr.destination in rel["history"]["booked_before"] and "something_went_wrong_before" in rel["history"]


# 4. routing by expertise -----------------------------------------------------------------------------------------

def test_requests_go_to_who_knows_the_destination_unless_they_are_much_busier(world):
    from brain.agents.triage import EXTRA_LOAD, best_specialist
    team = team_with_new_requests(world, 1)
    people = world.scalars(select(Employee).where(Employee.role == "specialist", Employee.team_id == team,
                                                  Employee.active.is_(True)).order_by(Employee.id)).all()
    expert, other = people[-1], people[0]
    dest = world.scalars(select(TripRequest).where(TripRequest.team_id == team)).first().destination
    for i in range(10):  # the expert owns the destination's knowledge
        world.add(KnowledgeItem(id=f"k-expert-note-{i}", title="x", body="x", destination=dest, topic="family", owner_id=expert.id,
                                status="approved", review_by=clock.today() + timedelta(days=90)))
    for t in world.scalars(select(TripRequest).where(TripRequest.specialist_id.in_([p.id for p in people]))).all():
        t.status = "lost"  # start from an empty desk for everyone
    world.commit()
    assert best_specialist(world, team, dest).id == expert.id
    fam = world.scalars(select(Family)).first()
    for i in range(EXTRA_LOAD + 1):
        world.add(TripRequest(id=f"busy{i}", family_id=fam.id, team_id=team, specialist_id=expert.id, destination=dest,
                              days=14, depart_month="mei", status="new"))
    world.commit()
    assert best_specialist(world, team, dest).id != expert.id  # too busy: the work is spread


# 5. partner scores -------------------------------------------------------------------------------------------------

def test_partner_scores_are_measured_and_a_weak_hotel_is_swapped(world):
    from brain import partner_scores
    from brain.agents.proposal import avoid_weak_partners
    from brain.db import PriceItem
    hotel = world.scalars(select(PriceItem).where(PriceItem.kind == "hotel")).first()
    alt = world.scalars(select(PriceItem).where(PriceItem.kind == "hotel", PriceItem.stop == hotel.stop,
                                                PriceItem.name != hotel.name)).first()
    p = world.scalars(select(Partner).where(Partner.name == hotel.name)).first()
    now = clock.utcnow()
    rids = [t.id for t in world.scalars(select(TripRequest).limit(4)).all()]
    for i in range(4):  # asked four times, answered once after 5 days, silent three times
        world.add(PartnerRequest(request_id=rids[i], partner_id=p.id, what="Room", status="answered" if i == 0 else "chased",
                                 sent_at=now - timedelta(days=20), answered_at=now - timedelta(days=15) if i == 0 else None))
    world.commit()
    partner_scores.measure(world)
    sc = partner_scores.scores(world.get(Partner, p.id))
    assert sc["measured"] and sc["avg_reply_days"] == 5.0 and sc["reliability"] == 0.25
    if alt:
        route = avoid_weak_partners(world, hotel.destination, [{"stop": hotel.stop, "nights": 2, "hotel": hotel.name}])
        assert route[0]["hotel"] != hotel.name and route[0]["swapped_from"] == hotel.name


# 6. gaps become knowledge ------------------------------------------------------------------------------------------

def test_a_family_question_the_brain_cannot_answer_teaches_it(world):
    fam = world.scalars(select(Family).where(Family.email.is_not(None))).first()
    q = "Hoi, mag onze hond mee in de huurauto op Bali? Groet"
    world.add(Mail(id="q1", received_at=clock.utcnow(), sender=fam.email, subject="Vraag over de hond", body=q, status="new", truth={}))
    world.commit()
    triage.triage_inbox(world)
    for _ in range(3):
        jobs.work(world, limit=50)
    d = world.scalars(select(Draft).where(Draft.kind == "answer")).all()
    d = next(x for x in d if (x.data or {}).get("mail_id") == "q1")
    assert d.data["gap_id"]
    gap_id = d.data["gap_id"]
    import pytest
    with pytest.raises(BlockedByCheck, match="placeholder"):
        approve_draft(world, d.id, "spec")
    answer = (f"Beste {fam.contact_name.split()[0]},\n\nHuisdieren mogen bij onze verhuurpartner op Bali niet mee in de "
              "huurauto. Voor een hond regelen we een aparte transfer met een gecertificeerde vervoerder.\n\nGroet,\nSanne")
    approve_draft(world, d.id, "spec", answer)
    item = world.get(KnowledgeItem, f"gap-{gap_id}")
    assert item.status == "proposed" and "gecertificeerde vervoerder" in item.body
    assert fam.contact_name.split()[0] not in item.body and "Beste" not in item.body and "Sanne" not in item.body
    assert world.get(KnowledgeGap, gap_id).status == "written"


# 7. search -----------------------------------------------------------------------------------------------------------

def test_search_understands_how_specialists_ask(world):
    from brain.evals.sets import KNOWLEDGE_PARAPHRASES, KNOWLEDGE_PARAPHRASES_HELD_OUT, KNOWLEDGE_QUESTIONS
    from brain.knowledge.store import searchable
    kb = KnowledgeBase(world)
    live = {i.id for i in world.scalars(searchable()).all()}
    for qs, need in ((KNOWLEDGE_QUESTIONS, 0.95), (KNOWLEDGE_PARAPHRASES, 0.85), (KNOWLEDGE_PARAPHRASES_HELD_OUT, 0.8)):
        qs = [x for x in qs if x[1] in live]
        hit = sum(want in [h.id for h in kb.search(q, k=3, role=role)] for q, want, role in qs)
        assert hit / len(qs) >= need, (qs[0][0], hit, len(qs))
    from brain.knowledge.concepts import destination_in
    assert destination_in("Twee weken Bali met de kids") == "indonesia" and destination_in("Zanzibar strand") == "tanzania"


def test_a_learned_example_carries_no_details_of_the_family_it_came_from(world):
    tr = new_requests(world, 1)[0]
    d = proposal.write_proposal(world, tr.id)
    approve_draft(world, d.id, "spec", d.body + "\n\nVoor Tim (8) en Noor (5) is de snorkeltocht ideaal. Bel ons op 06-12345678 of "
                                              "mail naar m.visser@ziggo.nl, wij wonen op Dorpsstraat 12 in Utrecht.")
    tr.status = "booked"
    world.commit()
    learning.learn_from_outcomes(world)
    ex = world.get(PastProposal, f"learned-{d.id}")
    if ex is not None:  # either cleaned, or not learned at all
        for leak in ("Tim", "Noor", "06-12345678", "m.visser@ziggo.nl", "Dorpsstraat 12"):
            assert leak not in ex.text, leak
