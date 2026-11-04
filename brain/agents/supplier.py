"""Supplier watcher (daily): changes in partner prices and availability, prices about to expire, slow or
unreliable partners. Findings go to the back office; nothing is changed automatically."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..db import Setting
from ..identity import agent
from ..toolserver import server
from .common import audit
from ..clock import utcnow
from ..clock import today as clock_today

ME = agent("supplier_watcher")


def watch(s: Session) -> dict:
    with audit(s, "supplier_watcher", "daily") as box:
        prices = server.call(s, ME, "prices.read")
        partners = {p["id"]: p for p in server.call(s, ME, "partners.list")}
        prev = s.get(Setting, "snapshot:prices")
        before = prev.value if prev else {}
        today = clock_today()
        findings = []
        for p in prices:
            vu = date.fromisoformat(p["valid_until"]) if p["valid_until"] else None
            who = partners.get(p["partner_id"], {}).get("name", p["name"])
            if vu and vu < today:
                findings.append({"kind": "price_expired", "partner": who, "item": p["name"], "destination": p["destination"],
                                 "detail": f"price valid until {vu.isoformat()}, ask for a new rate"})
            elif vu and vu < today + timedelta(days=30):
                findings.append({"kind": "price_expiring", "partner": who, "item": p["name"], "destination": p["destination"],
                                 "detail": f"price runs out on {vu.isoformat()}"})
            old = before.get(p["id"])
            if old is not None and abs(old - p["cost_eur"]) > 0.01:
                findings.append({"kind": "price_changed", "partner": who, "item": p["name"], "destination": p["destination"],
                                 "detail": f"cost changed from {old:.0f} to {p['cost_eur']:.0f} euro"})
        for p in partners.values():
            if p["kind"] != "airline" and (p["reliability"] < 0.7 or p["avg_reply_days"] > 3.5):
                findings.append({"kind": "slow_partner", "partner": p["name"], "item": "", "destination": p["destination"],
                                 "detail": f"replies in {p['avg_reply_days']} days on average, {round(p['reliability'] * 100)}% reliable"})
        s.merge(Setting(key="snapshot:prices", value={p["id"]: p["cost_eur"] for p in prices}))
        report = {"at": utcnow().isoformat(timespec="minutes"), "findings": findings}
        s.merge(Setting(key="report:supplier_watch", value=report))
        s.commit()
        box["output"] = f"{len(findings)} findings"
    return {"findings": len(findings)}
