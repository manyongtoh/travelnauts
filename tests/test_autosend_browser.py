"""The countdown on screen: a follow-up made after the switch shows 'Sends in … s' with Stop, and Stop works."""
from tests.security.test_xss_browser import server  # noqa: F401


def test_countdown_and_stop_on_screen(server, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright
    from sqlalchemy import select

    from brain import autosend, db
    from brain.clock import utcnow
    from brain.db import Draft, Setting, TripRequest
    base, env = server
    db.reset_engine(env["BRAIN_DATABASE_URL"])
    with db.session() as s:
        tr = s.scalars(select(TripRequest).where(TripRequest.specialist_id.is_not(None))).first()
        tr.status, who = "proposal_sent", tr.specialist_id
        s.merge(Setting(key=f"autosend:{who}:followup", value={"status": "on", "streak": 10, "on_by": who,
                                                                "on_at": utcnow().replace(microsecond=0).isoformat()}))
        s.commit()
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context()
        ctx.add_init_script(f"localStorage.setItem('me', '{who}')")
        p = ctx.new_page()
        p.goto(f"{base}/static/specialist.html")
        p.wait_for_selector(".aon", timeout=8000)  # the switch is visible, with Switch off
        with db.session() as s:
            d = Draft(kind="followup", request_id=tr.id, title="Nog vragen over jullie reis?", body="Hallo,\n\nNog vragen?\n\nGroet", data={})
            s.add(d)
            s.commit()
            did = d.id
        p.wait_for_selector(".acount", timeout=8000)
        assert "Sends in" in p.inner_text(".acount")
        p.screenshot(path=str(tmp_path / "countdown.png"))
        p.click(f'[data-stop="{did}"]')
        p.wait_for_timeout(1500)
        assert not p.query_selector(".acount")
        with db.session() as s:
            d = s.get(Draft, did)
            assert d.status == "draft" and d.data["auto_stopped"] == who and autosend.send_at(s, d) is None
        b.close()
    db.reset_engine()
