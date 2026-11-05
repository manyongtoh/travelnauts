"""Test #7: which family wrote this, when addresses are shared, new, forwarded or written differently.

Rule: an exact address match links by itself; anything else waits for a person, with suggestions. The brain
never links an unknown address to a family on its own, because its replies would then go to that address."""
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from brain.agents import triage
from brain.agents.triage import normalise_address, original_sender, resolve_family
from brain.clock import utcnow
from brain.db import AuditEntry, Employee, Family, FamilyAddress, Mail, TripRequest
from brain.tenant import tenant

NEW = SimpleNamespace(category="new_request", adults=2, child_ages=[7, 10])
CHANGE = SimpleNamespace(category="change", adults=None, child_ages=[])


def booked_family(s):
    tr = s.scalars(select(TripRequest).where(TripRequest.status == "booked")).first()
    return s.get(Family, tr.family_id), tr


def test_the_same_address_written_differently_is_the_same_family(world):
    fam, _ = booked_family(world)
    local, domain = fam.email.split("@")
    for variant in (fam.email.upper(), f"  {fam.email} ", f"{fam.contact_name} <{fam.email}>", f"{local}+reizen@{domain}"):
        assert resolve_family(world, variant, CHANGE)[0].id == fam.id, variant
    assert normalise_address("Marieke <Marieke.Visser+Trips@Ziggo.NL>") == "marieke.visser@ziggo.nl"


def test_the_other_parent_writing_from_their_own_address_is_not_linked_by_itself(world):
    fam, _ = booked_family(world)
    body = f"We willen graag een nacht langer blijven.\n\nGroet,\nKoen {fam.surname}"
    got, notes = resolve_family(world, "koen.partner@gmail.example", CHANGE, body, "Wijziging reis")
    assert got is None
    assert fam.id in [c["family_id"] for c in notes["candidates"]]  # suggested, because of the surname


def test_a_booking_number_is_a_suggestion_not_a_link(world):
    fam, tr = booked_family(world)
    got, notes = resolve_family(world, "iemand@anders.example", CHANGE, "Kunnen we de datum verschuiven?",
                                f"Re: {tenant().reference(tr.id)}")
    assert got is None
    c = next(c for c in notes["candidates"] if c["family_id"] == fam.id)
    assert any("booking" in w for w in c["why"])


def test_a_first_enquiry_from_the_other_parent_is_flagged_as_a_possible_duplicate(world):
    fam, _ = booked_family(world)
    body = f"Wij willen weer met jullie op reis, nu naar Japan.\n\nGroeten,\nKoen {fam.surname}"
    got, notes = resolve_family(world, "koen.partner@gmail.example", NEW, body, "Nieuwe reis")
    assert got.id.startswith("f-new-") and got.surname == fam.surname
    assert fam.id in [c["family_id"] for c in notes["possible_duplicate_of"]]


def test_one_address_shared_by_two_families_is_never_guessed(world):
    a, b = world.scalars(select(Family).limit(2)).all()
    b.email = a.email  # grandparents booking for two families, or a shared office address
    world.commit()
    got, notes = resolve_family(world, a.email, CHANGE)
    assert got is None and notes["shared_address"] and {c["family_id"] for c in notes["candidates"]} == {a.id, b.id}


def test_a_colleague_forwarding_a_family_mail_is_read_as_the_family(world):
    fam, _ = booked_family(world)
    body = (f"Zie hieronder, kun jij dit oppakken?\n\n---------- Doorgestuurd bericht ---------\nVan: {fam.contact_name} "
            f"<{fam.email}>\nDatum: 3 nov 2026\nOnderwerp: Vraag\n\nKunnen we een nacht langer blijven?")
    assert original_sender(f"sanne@{tenant().own_domains[0]}", body) == fam.email.lower()
    assert resolve_family(world, f"sanne@{tenant().own_domains[0]}", CHANGE, body)[0].id == fam.id
    assert original_sender("someone@gmail.example", body) == "someone@gmail.example"  # only our own colleagues' forwards


def test_a_person_links_the_mail_and_the_address_is_remembered(world):
    from brain.api import app as appmod
    appmod._buckets.clear()
    c = TestClient(appmod.app, raise_server_exceptions=False)
    fam, tr = booked_family(world)
    world.add(Mail(id="unk1", received_at=utcnow(), sender="Koen <koen.partner@gmail.example>", subject="Wijziging",
                   body=f"Kunnen we een nacht langer in het tweede hotel?\n\nGroet,\nKoen {fam.surname}", status="new", truth={}))
    world.commit()
    triage.triage_inbox(world)
    world.expire_all()
    m = world.get(Mail, "unk1")
    assert m.family_id is None and m.triage["unknown_sender"]
    lead = world.scalars(select(Employee).where(Employee.role == "team_lead", Employee.team_id == tr.team_id)).first()
    other = world.scalars(select(Employee).where(Employee.role == "back_office")).first()
    rows = c.get("/api/mails/unlinked", headers={"X-Brain-User": lead.id}).json()
    row = next(r for r in rows if r["id"] == "unk1")
    assert fam.id in [x["family_id"] for x in row["candidates"]]
    assert c.post("/api/mails/unk1/link", json={"family_id": fam.id}, headers={"X-Brain-User": other.id}).status_code == 403
    r = c.post("/api/mails/unk1/link", json={"family_id": fam.id}, headers={"X-Brain-User": lead.id}).json()
    assert r["address_remembered"] is True
    world.expire_all()
    assert world.get(FamilyAddress, "koen.partner@gmail.example").family_id == fam.id
    assert world.scalars(select(AuditEntry).where(AuditEntry.action == "link_mail")).first() is not None
    # next time the same parent writes, the brain knows them
    assert resolve_family(world, "koen.partner@gmail.example", CHANGE)[0].id == fam.id


def test_a_one_off_address_is_not_remembered(world):
    from brain.api import app as appmod
    appmod._buckets.clear()
    c = TestClient(appmod.app, raise_server_exceptions=False)
    fam, tr = booked_family(world)
    world.add(Mail(id="unk2", received_at=utcnow(), sender="hotel.lobby@hotel.example", subject="Vraag van familie",
                   body="Wij zitten in het hotel en hebben een vraag over de transfer.", status="new", truth={},
                   triage={"unknown_sender": True, "category": "question", "team_id": tr.team_id, "candidates": []}))
    world.commit()
    world.get(Mail, "unk2").status = "triaged"
    world.commit()
    lead = world.scalars(select(Employee).where(Employee.role == "team_lead", Employee.team_id == tr.team_id)).first()
    r = c.post("/api/mails/unk2/link", json={"family_id": fam.id, "remember_address": False}, headers={"X-Brain-User": lead.id}).json()
    assert r["address_remembered"] is False
    world.expire_all()
    assert world.get(FamilyAddress, "hotel.lobby@hotel.example") is None
