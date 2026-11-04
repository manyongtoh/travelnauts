"""Inventory of the existing n8n workflows (architecture: export, sort, rebuild what matters in code).

  brain n8n export.json [more.json ...]

For each workflow: trigger, systems it touches, credentials it uses, whether it holds business logic,
and a first suggestion: keep (works and simple), rebuild in code (holds business logic or touches
TravelSpirit with broad rights), or retire (inactive). The suggestion is a starting point for the talk
with the freelancers, not a decision. Credentials are listed by name only, never their content.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOGIC = {"n8n-nodes-base.code", "n8n-nodes-base.function", "n8n-nodes-base.functionItem", "n8n-nodes-base.if",
         "n8n-nodes-base.switch", "n8n-nodes-base.merge"}
TRIGGERS = ("Trigger", "webhook", "cron", "schedule")


def inventory(workflows: list[dict]) -> list[dict]:
    out = []
    for w in workflows:
        nodes = w.get("nodes", [])
        types = [n.get("type", "") for n in nodes]
        urls = [n.get("parameters", {}).get("url", "") for n in nodes]
        creds = sorted({c.get("name", k) for n in nodes for k, c in (n.get("credentials") or {}).items()})
        touches_ts = any("travelspirit" in (u or "").lower() for u in urls) or any("travelspirit" in c.lower() for c in creds)
        logic = [n["name"] for n in nodes if n.get("type") in LOGIC]
        trigger = next((n["type"].split(".")[-1] for n in nodes if any(t.lower() in n.get("type", "").lower() for t in TRIGGERS)), "manual")
        systems = sorted({t.split(".")[-1] for t in types if not any(x.lower() in t.lower() for x in TRIGGERS) and t not in LOGIC})
        if not w.get("active", True):
            advice, why = "retire", "inactive"
        elif logic or touches_ts:
            advice, why = "rebuild in code", ("holds business logic: " + ", ".join(logic)) if logic else "touches TravelSpirit"
        else:
            advice, why = "keep", "simple plumbing"
        out.append({"workflow": w.get("name"), "active": w.get("active", True), "trigger": trigger, "systems": systems,
                    "credentials": creds, "touches_travelspirit": touches_ts, "business_logic": logic, "advice": advice, "why": why})
    return out


def main(paths: list[str]) -> None:
    wfs = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        wfs += data if isinstance(data, list) else [data]
    rows = inventory(wfs)
    for r in rows:
        print(f"- {r['workflow']}: {r['advice']} ({r['why']}); trigger {r['trigger']}; systems {', '.join(r['systems']) or '-'}; "
              f"credentials {', '.join(r['credentials']) or '-'}")
    print("\nCheck the freelancers' contracts first: Travelnauts needs the rights to these workflows.")


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
