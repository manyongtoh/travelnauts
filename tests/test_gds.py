"""Booking commands in the client's booking system: Amadeus or Galileo, chosen in tenant.toml.

The brain only writes commands as text. The specialist runs them, all in one sitting from the Ready to book list,
so a system that asks for the authenticator after 10 idle minutes needs one login instead of one per booking.
"""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from brain.agents import gds
from brain.db import TripRequest
from brain.tenant import TenantConfig, tenant

SANNE = {"X-Brain-User": "sanne-de-vries"}
RUUD = {"X-Brain-User": "ruud-martens"}
NEVER = ("E", "ER", "ET", "TKP", "TTP", "XI", "XE")  # end, ticket or cancel


def _config(**change) -> TenantConfig:
    data = tenant().model_dump() | change
    return TenantConfig.model_validate(data)


def _use(monkeypatch, cfg: TenantConfig):
    import brain.sandbox_model
    import brain.tenant
    monkeypatch.setattr(brain.tenant, "tenant", lambda: cfg)
    monkeypatch.setattr(brain.sandbox_model, "tenant", lambda: cfg)


def _first_request(s):
    return s.scalars(select(TripRequest).order_by(TripRequest.id)).first()


def test_amadeus_commands(world):
    assert tenant().gds == "amadeus"
    d = gds.write_commands(world, _first_request(world).id)
    cmds = [c["cmd"] for c in d.data["commands"]]
    assert d.kind == "gds" and d.title.startswith("Amadeus:") and d.data["system"] == "amadeus"
    assert not [w for w in d.data["warnings"] if "onbekend formaat" in w]
    for start in ("AN", "SS", "NM1", "TKTL", "RF", "RT"):
        assert any(c.startswith(start) for c in cmds), start
    assert tenant().gds_agency_phone in cmds
    assert not any(c.split()[0] in NEVER for c in cmds)


def test_galileo_commands(world, monkeypatch):
    _use(monkeypatch, _config(gds="galileo", gds_agency_phone="P.AMSB*WOLKENWAAI"))
    d = gds.write_commands(world, _first_request(world).id)
    cmds = [c["cmd"] for c in d.data["commands"]]
    assert d.title.startswith("Galileo:") and not [w for w in d.data["warnings"] if "onbekend formaat" in w]
    assert any(c.startswith("N.") for c in cmds) and "*R" in cmds


def test_a_command_from_the_other_system_is_flagged():
    amadeus = [gds.Command(cmd="A15JUNAMSDPS", explain="Galileo availability")]
    assert gds.check(amadeus)  # the sample client runs Amadeus
    assert gds.check([gds.Command(cmd="ER", explain="end the booking")])  # ending is never allowed


def test_config_phone_must_fit_the_system():
    with pytest.raises(ValidationError, match="does not fit Amadeus"):
        _config(gds="amadeus", gds_agency_phone="P.AMSB*WOLKENWAAI")
    with pytest.raises(ValidationError):
        _config(gds="sabre")


def test_packs_written_for_galileo_still_load():
    data = tenant().model_dump()
    data.pop("gds"), data.pop("gds_agency_phone")
    cfg = TenantConfig.model_validate(data | {"galileo_agency_remark": "P.AMSB*WOLKENWAAI"})
    assert cfg.gds == "galileo" and cfg.gds_agency_phone == "P.AMSB*WOLKENWAAI"


def test_ready_to_book_list(world):
    from brain.api import app as appmod
    c = TestClient(appmod.app)
    appmod._buckets.clear()
    c.post("/api/triage", headers=SANNE)
    rids = [r["id"] for r in c.get("/api/requests", headers=SANNE).json()[:2]]
    made = [c.post(f"/api/requests/{rid}/gds", headers=SANNE).json()["id"] for rid in rids]
    ready = c.get("/api/gds/ready", headers=SANNE).json()
    assert ready["system"] == "Amadeus" and {i["id"] for i in ready["items"]} == set(made)
    assert not c.get("/api/gds/ready", headers=RUUD).json()["items"]  # another specialist sees none of hers
    assert c.post(f"/api/drafts/{made[0]}/approve", json={}, headers=SANNE).status_code == 200
    assert [i["id"] for i in c.get("/api/gds/ready", headers=SANNE).json()["items"]] == [made[1]]
