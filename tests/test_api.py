from fastapi.testclient import TestClient


def test_screens_and_main_flow(world):
    from brain.api.app import app
    c = TestClient(app)
    assert c.get("/static/specialist.html").status_code == 200
    assert c.get("/api/status").json()["data_stage"] == "synthetic"
    assert "truth" not in c.get("/api/inbox").json()[0]
    c.post("/api/triage")
    reqs = c.get("/api/requests").json()
    rid = next(r["id"] for r in reqs if r["mail_id"])
    d = c.post(f"/api/requests/{rid}/proposal").json()
    assert d["kind"] == "proposal"
    assert c.post(f"/api/drafts/{d['id']}/approve", json={"by": "test"}).status_code == 200
    assert c.post(f"/api/drafts/{d['id']}/approve", json={"by": "test"}).status_code == 409
    assert c.post(f"/api/requests/{rid}/partners").status_code == 200
    tl = c.get("/api/teamlead").json()
    assert set(tl["teams"]) == {"asia", "africa", "americas"}
    assert "specialist_id" not in str(tl["teams"])  # team figures only, nothing per person
    assert c.get("/api/backoffice").json()["cards"]
