"""Test bench: runs the agents over the synthetic inbox and checks them against the ground truth.

These are checks on correctness and safety (right team, right facts, no unsafe activities, sources
cited, gaps recorded), not the pilot's time savings. Time savings are measured in the pilot itself,
with real specialists, against the baseline (see the proposal's measurement plan).
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from .. import db
from ..agents import galileo, knowledge_desk, partner_desk, proposal, triage
from ..config import ROOT, get_settings
from ..db import Draft, Family, KnowledgeGap, Mail, PriceItem, TripRequest
from ..synth.generate import build


def pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def run(seed: int | None = None, out_dir: Path | None = None) -> dict:
    seed = seed if seed is not None else get_settings().seed
    build(seed)
    rep: dict = {"seed": seed, "model": get_settings().model}
    with db.session() as s:
        truth = {m.id: m.truth for m in s.scalars(select(Mail)).all()}
        t0 = time.perf_counter()
        results = triage.triage_inbox(s)
        triage_ms = (time.perf_counter() - t0) * 1000 / max(len(results), 1)
        mails = {m.id: m for m in s.scalars(select(Mail)).all()}

        # Triage ---------------------------------------------------------------------------
        cat_ok = dest_ok = dest_n = team_ok = team_n = 0
        fields = Counter()
        fields_n = 0
        confusion = Counter()
        for mid, m in mails.items():
            t, got = truth[mid], m.triage or {}
            confusion[(t["category"], got.get("category"))] += 1
            cat_ok += t["category"] == got.get("category")
            if t.get("destination") and t["category"] in ("new_request", "question"):
                dest_n += 1
                dest_ok += t["destination"] == got.get("destination")
            if t.get("team") and t["category"] in ("new_request", "question"):
                team_n += 1
                team_ok += t["team"] == got.get("team_id")
            if t["category"] == "new_request":
                fields_n += 1
                for f_truth, f_got in [("days", "days"), ("month", "month"), ("child_ages", "child_ages"),
                                       ("adults", "adults"), ("budget", "budget_eur")]:
                    a, b = t.get(f_truth), got.get(f_got)
                    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                        fields[f_truth] += float(a) == float(b)
                    else:
                        fields[f_truth] += a == b
        rep["triage"] = {
            "mails": len(mails), "category_accuracy_pct": pct(cat_ok, len(mails)),
            "destination_accuracy_pct": pct(dest_ok, dest_n), "team_routing_accuracy_pct": pct(team_ok, team_n),
            "field_accuracy_pct": {k: pct(v, fields_n) for k, v in fields.items()},
            "misclassified": [f"{a} -> {b} ({n})" for (a, b), n in confusion.items() if a != b],
            "avg_ms": round(triage_ms, 1)}

        # Proposals ------------------------------------------------------------------------
        reqs = list(s.scalars(select(TripRequest).where(TripRequest.mail_id.is_not(None))).all())
        ok = with_source = in_budget = budget_n = nights_ok = unsafe = 0
        ms = []
        for r in reqs:
            t0 = time.perf_counter()
            d = proposal.write_proposal(s, r.id)
            ms.append((time.perf_counter() - t0) * 1000)
            ok += 1
            with_source += any(x.get("type") == "knowledge" for x in d.sources)
            fam = s.get(Family, r.family_id)
            nights_ok += sum(x["nights"] for x in d.data["route"]) == r.days - 2
            youngest = min(fam.child_ages) if fam.child_ages else 18
            for stop in d.data["route"]:
                for a in stop["activities"]:
                    item = s.scalars(select(PriceItem).where(PriceItem.name == a)).first()
                    unsafe += bool(item and item.min_child_age > youngest)
            if r.budget_eur:
                budget_n += 1
                in_budget += d.data["price"]["sell_eur"] <= r.budget_eur * 1.05
        rep["proposals"] = {"requests": len(reqs), "drafted": ok, "with_knowledge_source_pct": pct(with_source, ok),
                            "route_fits_days_pct": pct(nights_ok, ok), "unsafe_activities": unsafe,
                            "within_budget_pct": pct(in_budget, budget_n),
                            "avg_ms": round(sum(ms) / len(ms), 1) if ms else None}

        # Knowledge desk -------------------------------------------------------------------
        qs = [(mid, t) for mid, t in truth.items() if t["category"] == "question"]
        right = answerable = gapped = unanswerable = wrong_confident = 0
        for mid, t in qs:
            res = knowledge_desk.ask(s, mails[mid].body.split("\n\n")[1], team_id=t.get("team"), mail_id=mid)
            if t.get("knowledge_id"):
                answerable += 1
                right += t["knowledge_id"] in res["cited"] and res["confident"]
            else:
                unanswerable += 1
                gapped += res["gap_id"] is not None
                wrong_confident += bool(res["confident"])
        rep["knowledge_desk"] = {"answerable": answerable, "answered_with_right_source_pct": pct(right, answerable),
                                 "unanswerable": unanswerable, "became_gap_pct": pct(gapped, unanswerable),
                                 "confident_but_should_not_be": wrong_confident,
                                 "open_gaps": s.query(KnowledgeGap).filter(KnowledgeGap.status == "open").count()}

        # Partner desk and Galileo on a sample -----------------------------------------------
        sample = reqs[:10]
        pr_ok = 0
        g_warn = g_cmds = 0
        for r in sample:
            d = s.scalars(select(Draft).where(Draft.request_id == r.id, Draft.kind == "proposal")).first()
            created = partner_desk.plan_partner_requests(s, r.id)
            pr_ok += len(created) == 1 + len(d.data["route"])
            g = galileo.write_commands(s, r.id)
            g_cmds += len(g.data["commands"])
            g_warn += sum("onbekend formaat" in w for w in g.data["warnings"])
        rep["partner_desk"] = {"sampled": len(sample), "right_number_of_requests_pct": pct(pr_ok, len(sample))}
        rep["galileo"] = {"sampled": len(sample), "commands": g_cmds, "format_warnings": g_warn}

    out_dir = out_dir or ROOT / "data" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    (out_dir / "report.md").write_text(to_markdown(rep))
    return rep


def to_markdown(rep: dict) -> str:
    lines = [f"# Test bench report", "", f"Model: `{rep['model']}` · seed {rep['seed']} · synthetic data", ""]
    for section in ("triage", "proposals", "knowledge_desk", "partner_desk", "galileo"):
        lines.append(f"## {section.replace('_', ' ').title()}")
        for k, v in rep[section].items():
            lines.append(f"- {k.replace('_', ' ')}: {v}")
        lines.append("")
    return "\n".join(lines)
