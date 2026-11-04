from fastapi.testclient import TestClient

SANNE = {"X-Brain-User": "sanne-de-vries"}
RUBEN = {"X-Brain-User": "ruben-stam"}
LEAD = {"X-Brain-User": "marloes-kuiper"}
ADMIN = {"X-Brain-User": "myt-beheer"}


def test_screens_and_main_flow(world):
    from brain.api.app import app
    c = TestClient(app)
    assert c.get("/static/specialist.html").status_code == 200
    assert c.get("/api/status").json()["data_stage"] == "synthetic"
    assert c.get("/api/inbox").status_code == 401
    assert "truth" not in c.get("/api/inbox", headers=SANNE).json()[0]
    c.post("/api/triage", headers=SANNE)
    reqs = c.get("/api/requests", headers=SANNE).json()
    assert reqs and all(r["specialist_id"] == "sanne-de-vries" for r in reqs)
    rid = next(r["id"] for r in reqs if r["mail_id"])
    d = c.post(f"/api/requests/{rid}/proposal", headers=SANNE).json()
    assert d["kind"] == "proposal"
    assert c.post(f"/api/drafts/{d['id']}/approve", json={}, headers=RUBEN).status_code == 403
    assert c.post(f"/api/drafts/{d['id']}/approve", json={}, headers=SANNE).status_code == 200
    assert c.post(f"/api/drafts/{d['id']}/approve", json={}, headers=SANNE).status_code == 409
    assert c.post(f"/api/requests/{rid}/partners", headers=SANNE).status_code == 200
    tl = c.get("/api/teamlead", headers=LEAD).json()
    assert set(tl["teams"]) == {"asia", "africa", "americas"}
    assert "specialist_id" not in str(tl["teams"])  # team figures only, nothing per person
    assert c.get("/api/teamlead", headers=SANNE).status_code == 403
    assert c.get("/api/backoffice", headers=RUBEN).json()["cards"]
    assert c.get("/api/metrics/teams.csv", headers=LEAD).text.startswith("date,team")


def test_admin_sees_no_customer_content_without_break_glass(world):
    from brain.api.app import app
    c = TestClient(app)
    c.post("/api/triage", headers=SANNE)
    rid = c.get("/api/requests", headers=SANNE).json()[0]["id"]
    assert c.get(f"/api/requests/{rid}", headers=ADMIN).status_code == 403
    assert c.get("/api/requests", headers=ADMIN).json() == []
    h = c.get("/api/admin/health", headers=ADMIN).json()
    assert h["audit_chain"]["ok"] and "agents" in h
    assert c.get("/api/admin/health", headers=LEAD).status_code == 403
    mid = c.get("/api/inbox", headers=ADMIN).json()[0]["id"]
    assert c.post(f"/api/admin/break-glass/mail/{mid}", json={"reason": "short"}, headers=ADMIN).status_code == 400
    assert c.post(f"/api/admin/break-glass/mail/{mid}", json={"reason": "customer asked for a copy of their data"}, headers=ADMIN).status_code == 200
    chain = c.get("/api/admin/audit-chain", headers=ADMIN).json()
    assert chain["verify"]["ok"] and chain["entries"][0]["action"] == "break_glass"


def test_user_management_and_pausing(world):
    from brain.api.app import app
    c = TestClient(app)
    assert c.post("/api/admin/users", json={"name": "Test Persoon", "email": "t@x", "role": "specialist", "team_id": "africa"},
                  headers=LEAD).status_code == 403
    assert c.post("/api/admin/users", json={"name": "Test Persoon", "email": "t@x", "role": "specialist", "team_id": "asia"},
                  headers=LEAD).status_code == 200
    assert c.post("/api/admin/users/test-persoon", json={"active": False}, headers=LEAD).status_code == 200
    assert c.get("/api/inbox", headers={"X-Brain-User": "test-persoon"}).status_code == 401
    assert c.post("/api/admin/agents/triage/pause", json={"paused": True}, headers=ADMIN).status_code == 200
    r = c.post("/api/jobs/run/poll_inbox", headers=ADMIN).json()
    assert r["status"] == "queued"  # paused: the job waits
    c.post("/api/admin/agents/triage/pause", json={"paused": False}, headers=ADMIN)
