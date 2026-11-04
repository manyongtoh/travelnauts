from sqlalchemy import select

from brain.agents import change, triage
from brain.agents.change import ChangeOp, apply_ops
from brain.db import Mail, TripRequest
from brain.workflow import approve_draft


def test_change_mails_are_linked_to_the_right_trip(world):
    triage.triage_inbox(world)
    changes = [m for m in world.scalars(select(Mail)).all() if m.truth.get("category") == "change"]
    assert changes
    for m in changes:
        assert m.triage["request_id"] == m.truth["request_id"]
        assert world.get(TripRequest, m.truth["request_id"]).status == "change_requested"


def test_change_is_applied_priced_and_needs_approval(world):
    triage.triage_inbox(world)
    for m in [m for m in world.scalars(select(Mail)).all() if m.truth.get("category") == "change"]:
        d = change.handle_change(world, m.id)
        exp = [(o["op"], o["stop"], o["nights"]) for o in m.truth["ops"]]
        assert [(o["op"], o["stop"], o["nights"]) for o in d.data["ops"]] == exp
        assert d.status == "draft"
        assert d.data["days_after"] == sum(r["nights"] for r in d.data["route"]) + 2
        if m.truth["ops"][0]["op"] in ("shift_dates", "swap_transport"):
            assert d.data["manual"] and d.data["route"] == d.data["route_before"]
        else:
            assert d.data["applied"] and d.data["price"]["sell_eur"] != d.data["price_before"]["sell_eur"]
    approve_draft(world, d.id, "test")
    tr = world.get(TripRequest, d.request_id)
    assert tr.status == "proposal_sent" and tr.days == d.data["days_after"]


def test_unsafe_changes_go_to_the_specialist():
    route = [{"stop": "A", "nights": 2, "hotel": "a"}, {"stop": "B", "nights": 3, "hotel": "b"}, {"stop": "C", "nights": 4, "hotel": "c"}]
    new, applied, manual = apply_ops(route, [ChangeOp(op="remove_stop", stop="A"), ChangeOp(op="shorten_stop", stop="B", nights=5),
                                             ChangeOp(op="extend_stop", stop="Nowhere", nights=1), ChangeOp(op="remove_stop", stop="B")])
    assert [r["stop"] for r in new] == ["A", "C"]
    assert len(applied) == 1 and len(manual) == 3


def test_hard_set_runs_end_to_end_without_crashing(tmp_path):
    from brain import db
    from brain.agents.knowledge_desk import ask
    from brain.synth.generate import build
    db.reset_engine(f"sqlite:///{tmp_path / 'hard.db'}")
    build(seed=3, n_families=60, hard=True)
    with db.session() as s:
        hard = [m for m in s.scalars(select(Mail)).all() if m.truth.get("set") == "hard"]
        assert len(hard) >= 30
        results = triage.triage_inbox(s)
        assert len(results) == s.query(Mail).count()
        for m in hard:
            if m.triage.get("category") == "change" and m.triage.get("request_id"):
                change.handle_change(s, m.id)
            if m.truth["category"] == "question":
                ask(s, m.body)
    db.reset_engine()
