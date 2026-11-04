"""Stored XSS: hostile text in mails, names and knowledge must never run in a colleague's browser."""
from brain.clock import utcnow
import os
import socket
import subprocess
import sys
import time
from datetime import datetime

import pytest

PAYLOADS = ['<img src=x onerror="window.__xss=1">', '"><svg onload="window.__xss=2">', "<script>window.__xss=3</script>",
            "javascript:window.__xss=4", "'><iframe srcdoc=\"<script>parent.__xss=5</script>\">"]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture()
def server(tmp_path):
    pytest.importorskip("playwright.sync_api")
    env = os.environ | {"BRAIN_DATABASE_URL": f"sqlite:///{tmp_path / 'x.db'}", "BRAIN_VAULT": str(tmp_path / "v"),
                        "BRAIN_FILES": str(tmp_path / "f"), "PYDANTIC_AI_NO_BANNER": "1"}
    code = f"""
from brain.synth.generate import build
from brain import db
from brain.db import Mail, Family, KnowledgeItem
from brain.agents import triage, proposal
from datetime import datetime, date, timedelta
from brain.clock import utcnow
build(seed=5, n_families=40, hard=False)
P = {PAYLOADS!r}
with db.session() as s:
    f = s.get(Family, "fam001"); f.contact_name = P[0] + " " + P[1]; f.surname = P[2]
    s.add(Mail(id="xss1", received_at=utcnow(), sender="a@example.org", subject=P[1] + " Thailand",
               body="Hallo,\\n\\nWij willen in juli naar Thailand, 21 dagen. We zijn met 2 volwassenen en 1 kinderen (6 jaar).\\n" + P[0] + P[1] + P[3],
               family_id="fam001", truth={{}}))
    s.add(Mail(id="xss2", received_at=utcnow(), sender="b@example.org", subject=P[2] + P[4], body=" ".join(P),
               family_id="fam002", truth={{}}))  # this one is flagged as suspicious and shown to the team lead
    s.add(KnowledgeItem(id="k-xss", title="Reistijd Thailand " + P[0], body="Beste reistijd Thailand " + " ".join(P), destination="thailand",
               topic="season", owner_id="noor-visser", status="approved", review_by=date.today() + timedelta(days=30)))
    s.commit()
    triage.triage_inbox(s)
"""
    subprocess.run([sys.executable, "-c", code], env=env, check=True, cwd=os.getcwd())
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "brain.api.app:app", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(120):  # wait until the server answers, not a fixed time
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    yield f"http://127.0.0.1:{port}", env
    proc.terminate()


def test_no_script_runs_from_stored_text(server):
    from playwright.sync_api import sync_playwright
    base, env = server
    import sqlite3
    db = sqlite3.connect(env["BRAIN_DATABASE_URL"].removeprefix("sqlite:///"))
    owner = db.execute("select specialist_id from requests where mail_id='xss1'").fetchone()[0]
    fired = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for user, page, clicks in [(owner, "specialist.html", [".ditem"]), (owner, "specialist.html", ["[data-view=ask]"]),
                                   ("marloes-kuiper", "teamlead.html", []), ("marloes-kuiper", "teamlead.html", ["[data-view=knowledge]"]), ("ruben-stam", "backoffice.html", []),
                                   ("myt-beheer", "maintenance.html", ["[data-view=audit]"]), ("myt-beheer", "users.html", [])]:
            ctx = b.new_context()
            ctx.add_init_script(f"localStorage.setItem('me', '{user}')")
            p = ctx.new_page()
            p.on("dialog", lambda d: (fired.append(("dialog", d.message)), d.dismiss()))
            p.goto(f"{base}/static/{page}")
            p.wait_for_timeout(1200)
            for sel in clicks:
                if p.query_selector(sel):
                    p.click(sel)
                    p.wait_for_timeout(1000)
            if page == "specialist.html" and clicks == ["[data-view=ask]"]:
                p.fill("#q", "beste reistijd thailand")
                p.click("#ask")
                p.wait_for_timeout(1000)
            if page == "specialist.html" and clicks == [".ditem"]:
                assert "onerror" in p.inner_text("body")  # the hostile text is on screen, shown as text
            if page == "teamlead.html" and not clicks:
                assert "<script>" in p.inner_text("body")  # the flagged mail's subject, shown as text
            if p.evaluate("window.__xss"):
                fired.append((page, p.evaluate("window.__xss")))
            ctx.close()
        b.close()
    assert not fired, fired
