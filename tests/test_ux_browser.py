"""Usability guards: destructive buttons ask once more in place, labels and landmarks are there, a skip link works."""
from tests.security.test_xss_browser import server  # noqa: F401


def test_remove_access_needs_a_second_click(server):  # noqa: F811
    import sqlite3

    from playwright.sync_api import sync_playwright
    base, env = server
    con = sqlite3.connect(env["BRAIN_DATABASE_URL"].removeprefix("sqlite:///"))
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context()
        ctx.add_init_script("localStorage.setItem('me', 'myt-beheer')")
        p = ctx.new_page()
        p.goto(f"{base}/static/users.html")
        p.wait_for_selector("[data-confirm]")
        btn = next(x for x in p.query_selector_all("[data-confirm]") if x.get_attribute("data-active") != "myt-beheer")  # not yourself
        uid = btn.get_attribute("data-active")
        btn.click()
        p.wait_for_timeout(600)
        assert "Click again" in btn.inner_text()
        assert con.execute("select active from employees where id=?", (uid,)).fetchone()[0] == 1  # nothing happened yet
        btn.click()
        p.wait_for_timeout(1200)
        assert con.execute("select active from employees where id=?", (uid,)).fetchone()[0] == 0
        # landmarks, skip link, labelled fields
        assert p.query_selector("header") and p.query_selector("main#view") and p.query_selector("nav[aria-label]")
        first = p.evaluate("document.querySelector('a[href],button,select,input,textarea').className")
        assert first == "skip"  # the first thing a keyboard reaches is "Skip to content"
        unlabeled = p.evaluate("""() => [...document.querySelectorAll('select,input,textarea')].filter(e =>
            !e.getAttribute('aria-label') && !e.closest('label') && !(e.id && document.querySelector(`label[for="${e.id}"]`))).length""")
        assert unlabeled == 0
        b.close()
