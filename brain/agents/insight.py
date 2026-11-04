"""Customer insight (nightly) and team insight (hourly). Totals only, per team, never per person."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..db import Setting
from ..identity import agent
from ..synth.world import DESTINATIONS
from ..toolserver import server
from .common import audit


def customer_insight(s: Session) -> dict:
    with audit(s, "customer_insight", "nightly") as box:
        rows = server.call(s, agent("customer_insight"), "stats.requests")
        per_team = defaultdict(list)
        for r in rows:
            per_team[r["team_id"] or "none"].append(r)
        report = {"at": datetime.utcnow().isoformat(timespec="minutes"), "teams": {}}
        for team, rs in per_team.items():
            booked = sum(r["status"] == "booked" for r in rs)
            offered = sum(r["status"] in ("proposal_sent", "booked", "lost") for r in rs)
            budgets = [r["budget_eur"] for r in rs if r["budget_eur"]]
            report["teams"][team] = {
                "requests": len(rs),
                "top_destinations": [[DESTINATIONS[d]["name"], n] for d, n in Counter(r["destination"] for r in rs).most_common(4)],
                "top_months": Counter(r["depart_month"] for r in rs if r["depart_month"] != "onbekend").most_common(3),
                "top_wishes": Counter(w for r in rs for w in r["wishes"]).most_common(4),
                "avg_trip_days": round(sum(r["days"] for r in rs) / len(rs), 1) if rs else None,
                "avg_budget_eur": round(sum(budgets) / len(budgets), -2) if budgets else None,
                "booked_share_pct": round(100 * booked / offered, 1) if offered else None,
            }
        s.merge(Setting(key="report:customer_insight", value=report))
        s.commit()
        box["output"] = f"{len(rows)} requests over {len(per_team)} teams"
    return {"requests": len(rows)}


STUCK = {"new": timedelta(days=2), "proposal_draft": timedelta(days=2), "change_requested": timedelta(days=1)}


def team_insight(s: Session) -> dict:
    with audit(s, "team_insight", "hourly") as box:
        rows = server.call(s, agent("team_insight"), "stats.requests")
        now = datetime.utcnow()
        report = {"at": now.isoformat(timespec="minutes"), "teams": {}}
        per_team = defaultdict(list)
        for r in rows:
            per_team[r["team_id"] or "none"].append(r)
        for team, rs in per_team.items():
            stuck = []
            for r in rs:
                since = datetime.fromisoformat(r["last_change"]) if r["last_change"] else None
                limit = STUCK.get(r["status"])
                if limit and since and now - since > limit:
                    stuck.append({"request_id": r["id"], "status": r["status"], "days": (now - since).days})
            leads = [r["hours_to_first_draft"] for r in rs if r["hours_to_first_draft"] is not None]
            report["teams"][team] = {
                "open": sum(r["status"] in ("new", "proposal_draft", "proposal_sent", "change_requested") for r in rs),
                "waiting_for_specialist": sum(r["status"] in ("new", "proposal_draft", "change_requested") for r in rs),
                "avg_hours_to_first_draft": round(sum(leads) / len(leads), 2) if leads else None,
                "stuck": sorted(stuck, key=lambda x: -x["days"])[:10],
            }
        s.merge(Setting(key="report:team_insight", value=report))
        s.commit()
        box["output"] = f"{sum(len(t['stuck']) for t in report['teams'].values())} stuck requests"
    return {"teams": len(per_team)}
