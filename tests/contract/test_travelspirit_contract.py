"""Contract tests: recorded TravelSpirit responses must still map onto the platform's objects.
If TravelSpirit renames or drops a field, these fail in CI long before pilot or live."""
import json
from pathlib import Path

from brain.travelspirit import adapter_v1

REC = Path(__file__).parent / "recorded"


def load(name):
    return json.loads((REC / f"{name}.json").read_text())


def test_mail_contract():
    m = adapter_v1.to_mail(load("mail"))
    assert set(m) == {"id", "received_at", "sender", "subject", "body", "family_id", "dossier_id"}
    assert m["family_id"] == "ts-relation-4411" and m["received_at"].startswith("2026-11-02T08:14")


def test_relation_contract():
    r = adapter_v1.to_relation(load("relation"))
    assert r["adults"] == 2 and r["child_ages"] == [6, 9] and r["id"] == "ts-relation-4411"


def test_dossier_contract():
    d = adapter_v1.to_dossier(load("dossier"))
    assert d["status"] == "proposal_sent" and d["destination"] == "thailand" and d["days"] == 21
