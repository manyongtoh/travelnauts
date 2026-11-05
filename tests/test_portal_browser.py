"""The partner's page works without an account and on a phone; the back office sees the answer in the panel."""
from tests.security.test_xss_browser import server  # noqa: F401


def test_portal_on_a_phone_and_the_panel(server, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright
    from sqlalchemy import select
    from brain import db, portal
    from brain.agents import proposal
    from brain.db import Partner, PartnerRequest, TripRequest
    base, env = server
    db.reset_engine(env["BRAIN_DATABASE_URL"])
    with db.session() as s:
        tr = next(t for t in s.scalars(select(TripRequest)).all()
                  if s.scalars(select(Partner).where(Partner.destination == t.destination, Partner.kind == "local_agent")).first())
        proposal.write_proposal(s, tr.id)
        p = s.scalars(select(Partner).where(Partner.destination == tr.destination, Partner.kind == "local_agent")).first()
        pr = PartnerRequest(request_id=tr.id, partner_id=p.id, what="Transfers and excursions", status="waiting")
        s.add(pr)
        s.commit()
        url, prid = portal.issue_link(s, pr), pr.id
    token = url.rsplit("/", 1)[1]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        phone = b.new_context(viewport={"width": 390, "height": 844})
        pg = phone.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{base}/portal/{token}")
        pg.wait_for_selector(".line select")
        first = pg.query_selector(".line")
        first.query_selector('[data-f="status"]').select_option("confirmed")
        first.query_selector('[data-f="price"]').fill("95")
        first.query_selector('[data-f="save"]').click()
        pg.wait_for_timeout(800)
        assert "Saved" in pg.inner_text(".line")
        second = pg.query_selector_all(".line")[1]
        second.query_selector('[data-f="status"]').select_option("alternative")
        second.query_selector('[data-f="alt"]').fill('<img src=x onerror="window.__xss=9"> Riverside Lodge')
        second.query_selector('[data-f="altprice"]').fill("200")
        second.query_selector('[data-f="save"]').click()
        pg.wait_for_timeout(800)
        pg.screenshot(path=str(tmp_path / "portal-phone.png"), full_page=True)
        assert pg.evaluate("document.documentElement.scrollWidth") <= 392  # no sideways scrolling on a phone
        pg.screenshot(path=str(tmp_path / "portal-phone.png"), full_page=True)
        assert not pg.evaluate("window.__xss") and not errors, errors

        ctx = b.new_context()
        ctx.add_init_script("localStorage.setItem('me', 'ruben-stam')")
        bo = ctx.new_page()
        bo.goto(f"{base}/static/backoffice.html")
        bo.wait_for_timeout(1500)
        bo.evaluate(f"openPortal({prid})")
        bo.wait_for_selector(".portalpanel [data-accept]")
        assert "Riverside Lodge" in bo.inner_text(".portalpanel") and not bo.evaluate("window.__xss")
        bo.screenshot(path=str(tmp_path / "panel.png"))
        bo.click(".portalpanel [data-accept]")
        bo.wait_for_timeout(1000)
        assert "Accept alternative" not in bo.inner_text(".portalpanel")
        b.close()
    db.reset_engine()
