from fastapi.testclient import TestClient

from tests.test_api import LEAD, SANNE


def test_value_dashboard_counts_and_baseline(world):
    from brain.api.app import app
    c = TestClient(app)
    c.post("/api/triage", headers=SANNE)
    rid = next(r["id"] for r in c.get("/api/requests", headers=SANNE).json() if r["mail_id"])
    d = c.post(f"/api/requests/{rid}/proposal", headers=SANNE).json()
    assert c.post(f"/api/drafts/{d['id']}/approve", json={}, headers=SANNE).status_code == 200

    assert c.get("/api/value", headers=SANNE).status_code == 403  # team figures are for the team lead
    r = c.get("/api/value?days=30", headers=LEAD).json()
    assert r["quality"]["per_kind"]["proposal"]["sent"] >= 1
    assert r["speed"]["median_hours_to_first_proposal_draft"] is not None
    assert r["baseline"]["measured"] is False and r["hours_saved_estimate"] > 0
    assert "specialist" not in str(r)  # never per person

    team = c.get("/api/value?team=asia", headers=LEAD).json()
    other = c.get("/api/value?team=nowhere", headers=LEAD).json()
    assert other["speed"]["requests"] == 0 and other["quality"]["drafts_decided"] == 0
    assert team["speed"]["requests"] <= r["speed"]["requests"]

    before = r["minutes_saved_estimate"]
    assert c.post("/api/value/baseline", json={"minutes": {"proposal": -5}}, headers=LEAD).status_code == 400
    assert c.post("/api/value/baseline", json={"minutes": {"proposal": 180, "hack": 9}, "measured": True}, headers=LEAD).status_code == 200
    r2 = c.get("/api/value", headers=LEAD).json()
    assert r2["baseline"]["measured"] is True and "hack" not in r2["baseline"]["minutes"]
    assert r2["minutes_saved_estimate"] > before
    assert c.get("/api/value.csv", headers=LEAD).text.startswith("measure,value")
