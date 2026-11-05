"""Dutch and English: the switch translates the screens, never customer text, and is remembered per person."""
from tests.security.test_xss_browser import (
    server,  # noqa: F401  (same seeded server, hostile text included)
)


def test_dutch_switch(server, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright
    base, _ = server
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context()
        ctx.add_init_script("localStorage.setItem('me', 'marloes-kuiper')")
        p = ctx.new_page()
        errors = []
        p.on("pageerror", lambda e: errors.append(str(e)))
        p.goto(f"{base}/static/teamlead.html")
        p.wait_for_timeout(1200)
        assert "Overview" in p.inner_text("nav")
        p.click('.lang[data-lang="nl"]')
        p.wait_for_timeout(1500)
        nav = p.inner_text("nav")
        assert "Overzicht" in nav and "Kennishiaten" in nav and "Overview" not in nav
        assert p.evaluate("document.documentElement.lang") == "nl"
        body = p.inner_text("body")
        assert "open aanvragen" in body and "<script>" in body  # hostile subject still shown as text, untouched
        assert not p.evaluate("window.__xss")
        p.click('[data-view="value"]')
        p.wait_for_timeout(1000)
        assert "Wat het brein oplevert" in p.inner_text("#view")
        p.screenshot(path=str(tmp_path / "nl.png"))
        for view in ("duplicates", "insight", "knowledge", "gaps", "complaints", "log"):
            p.click(f'[data-view="{view}"]')
            p.wait_for_timeout(700)
        p.click('[data-view="duplicates"]')
        p.wait_for_timeout(800)
        assert "Dubbele families" in p.inner_text("#view")
        p.reload()  # remembered for this person
        p.wait_for_timeout(1200)
        assert "Overzicht" in p.inner_text("nav")
        p.click('.lang[data-lang="en"]')
        p.wait_for_timeout(1500)
        assert "Overview" in p.inner_text("nav")
        assert not errors, errors
        b.close()
