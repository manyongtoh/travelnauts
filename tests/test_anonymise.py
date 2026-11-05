import json

import pytest

from brain.anonymise import Anonymiser, Refused, anonymise_mail

PII_MAIL = """Beste Sanne,

Mijn man Pieter en ik willen in april drie weken naar Japan. Onze dochter Lotte is 7 en zoon Bram is 10.
Budget ongeveer 16000 euro. Paspoortnummer: NXK4R81P2. IBAN NL91ABNA0417164300.
Geboren op 12-03-1984. BSN 111222333.

Met vriendelijke groet,
Anouk de Wit
Kerkstraat 12
3512 AB Utrecht
+31 6 1234 5678
anouk.dewit@gmail.com"""


def test_removes_every_kind_of_personal_data():
    r = Anonymiser().scrub(PII_MAIL, ["Anouk de Wit"])
    for leaked in ["Pieter", "Anouk", "Wit", "NXK4R81P2", "NL91ABNA0417164300", "12-03-1984", "111222333",
                   "Kerkstraat", "3512 AB", "1234 5678", "gmail"]:
        assert leaked not in r.text, leaked
    assert r.ok


def test_keeps_what_the_agents_need():
    r = Anonymiser().scrub(PII_MAIL, ["Anouk de Wit"])
    for kept in ["april", "drie weken", "Japan", "is 7", "is 10", "16000 euro"]:
        assert kept in r.text, kept


def test_keeps_hotels_and_places_that_look_like_names():
    r = Anonymiser().scrub("Hoi,\n\nKunnen we in Hoi An Garden Villas een nacht langer?\n\nGroet, Joris Smit", [])
    assert "Hoi An Garden Villas" in r.text and "Joris" not in r.text


def test_refuses_when_unsure():
    with pytest.raises(Refused):
        Anonymiser().scrub("Mail me op femke(at)gmail(dot)com, klantnummer A1B2C3D4E5.", [])


def test_same_person_gets_the_same_tag_and_no_key_is_kept():
    r = Anonymiser().scrub("Hallo,\n\nGroet, Femke Meijer\n\nPS Femke Meijer belt morgen.", ["Femke Meijer"])
    tags = {t for t in r.text.split() if t.startswith("[NAAM")}
    assert len({t.strip(".,") for t in tags}) == 1
    assert "Femke" not in json.dumps(r.summary())


def test_mail_keeps_only_the_sender_domain_for_businesses():
    out, _ = anonymise_mail({"sender": "anouk@gmail.com", "subject": "Japan", "body": "Hallo,\n\nJapan in april?"})
    assert out["sender_domain"] == "freemail" and "anouk" not in json.dumps(out)
    out, _ = anonymise_mail({"sender": "booking@hoi-an-garden-villas.example", "subject": "Offer", "body": "Dear team"})
    assert out["sender_domain"] == "hoi-an-garden-villas.example"


def test_all_synthetic_mails_pass_and_triage_the_same(world):
    from sqlalchemy import select

    from brain.db import Family, Mail
    from brain.sandbox_model import triage
    from brain.synth.world import DESTINATIONS
    dests = {k: v["nl"] for k, v in DESTINATIONS.items()}
    for m in world.scalars(select(Mail)).all():
        f = world.get(Family, m.family_id) if m.family_id else None
        out, _ = anonymise_mail({"sender": m.sender, "subject": m.subject, "body": m.body},
                                {"contact_name": f.contact_name, "surname": f.surname} if f else None)
        a = triage({"destinations": dests, "mail": {"from": m.sender, "subject": m.subject, "body": m.body}})
        b = triage({"destinations": dests, "mail": {"from": out["sender_domain"], "subject": out["subject"], "body": out["body"]}})
        assert {k: a.get(k) for k in ("category", "destination", "days", "child_ages")} == \
               {k: b.get(k) for k in ("category", "destination", "days", "child_ages")}, m.id


def test_ingest_needs_the_anonymised_stage_and_skips_refused(tmp_path, monkeypatch):
    from brain import db
    from brain.ingest import ingest
    export = tmp_path / "export.jsonl"
    export.write_text("\n".join(json.dumps(x) for x in [
        {"type": "relation", "id": "R1", "contact_name": "Anouk de Wit", "surname": "de Wit", "adults": 2, "child_ages": [7, 10]},
        {"type": "mail", "id": "M1", "relation_id": "R1", "received_at": "2026-11-01T09:00:00", "sender": "anouk@gmail.com",
         "subject": "Japan", "body": PII_MAIL},
        {"type": "mail", "id": "M2", "relation_id": "R1", "received_at": "2026-11-01T10:00:00", "sender": "anouk@gmail.com",
         "subject": "Nog iets", "body": "Mail me op anouk(at)gmail(dot)com"},
    ]))
    db.reset_engine(f"sqlite:///{tmp_path / 'a.db'}")
    db.create_all()
    with pytest.raises(RuntimeError):
        ingest(export)
    monkeypatch.setenv("BRAIN_DATA_STAGE", "anonymised")
    rep = ingest(export)
    assert rep["mails"] == 1 and rep["refused"][0]["id"] == "M2" and "EMAIL_LIKE" in rep["refused"][0]["reasons"]
    with db.session() as s:
        from brain.db import Family, Mail
        assert "Wit" not in json.dumps([m.body for m in s.query(Mail).all()])
        assert s.query(Family).one().email is None
    db.reset_engine()
