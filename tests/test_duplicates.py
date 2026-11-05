"""Duplicate families: found with evidence, merged only by a person, mail keeps finding the family afterwards."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_api import LEAD, SANNE


def test_find_merge_and_keep_apart(world):
    from brain import duplicates
    from brain.agents.triage import families_for_address
    from brain.api.app import app
    from brain.db import Family, TripRequest
    a = world.get(Family, "fam001")
    twin = Family(id="fam900", surname=a.surname, contact_name="Ander " + a.surname, email="tweede.ouder@kpn.example", adults=2,
                  child_ages=list(a.child_ages), child_birth_years=list(a.child_birth_years), city=a.city, synthetic=True)
    world.add(twin)
    world.add(TripRequest(id="r900", family_id="fam900", destination="japan", days=14, depart_month="mei", status="booked"))
    world.commit()
    c = TestClient(app)
    assert c.get("/api/duplicates", headers=SANNE).status_code == 403
    rows = c.get("/api/duplicates", headers=LEAD).json()
    pair = next(r for r in rows if {r["keep"], r["drop"]} == {"fam001", "fam900"})
    assert pair["level"] == "likely" and any("children born" in e for e in pair["evidence"])
    noise = [r for r in rows if "fam900" not in (r["keep"], r["drop"])]
    assert len(noise) <= 3, noise  # the synthetic families are distinct: few false alarms
    assert "fam001" in c.get("/api/duplicates.csv", headers=LEAD).text

    res = c.post("/api/duplicates/merge", json={"keep": "fam001", "drop": "fam900"}, headers=LEAD).json()
    assert res["moved"]["trips"] == 1 and res["moved"]["addresses"] == 1
    world.expire_all()
    assert world.get(TripRequest, "r900").family_id == "fam001"
    assert [f.id for f in families_for_address(world, "tweede.ouder@kpn.example")] == ["fam001"]  # their mail still lands
    assert duplicates.merged_into(world.get(Family, "fam900")) == "fam001"
    assert not any("fam900" in (r["keep"], r["drop"]) for r in c.get("/api/duplicates", headers=LEAD).json())
    assert c.post("/api/duplicates/merge", json={"keep": "fam001", "drop": "fam900"}, headers=LEAD).status_code == 409
    assert "merged in the brain" in c.get("/api/duplicates.csv", headers=LEAD).text

    if noise:
        n = noise[0]
        c.post("/api/duplicates/apart", json={"keep": n["keep"], "drop": n["drop"]}, headers=LEAD)
        assert not any({r["keep"], r["drop"]} == {n["keep"], n["drop"]} for r in c.get("/api/duplicates", headers=LEAD).json())


def test_new_relation_from_the_other_parent_is_suggested(world):
    from brain import duplicates
    from brain.agents import triage
    from brain.clock import utcnow
    from brain.db import Family, Mail
    f = next(x for x in world.scalars(select(Family).order_by(Family.id)).all() if x.child_birth_years)
    world.add(Mail(id="dup1", received_at=utcnow(), sender="papa.nieuw@gmail.example", subject="Reis naar Japan",
                   body=f"Hallo, wij willen in juli 3 weken naar Japan met de kinderen.\n\nGroet,\nKees {f.surname}", status="new", truth={}))
    world.commit()
    triage.triage_mail(world, "dup1")
    m = world.get(Mail, "dup1")
    assert m.family_id.startswith("f-new-")  # an unknown address with a first request opens a new relation
    assert any(f.id in (r["keep"], r["drop"]) and m.family_id in (r["keep"], r["drop"]) for r in duplicates.candidates(world))
