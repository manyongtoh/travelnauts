"""Test bench: runs the agents over the synthetic inbox and checks them against the ground truth.

Two sets: "clean" (the regular synthetic mails) and "hard" (written the way people really write; see
synth/hard.py). The stand-in model's rules were written against the clean set only, so the hard set
shows how brittle rules are, and is the yardstick for a real model.

These are checks on correctness and safety, not the pilot's time savings. Time savings are measured in
the pilot with real specialists against the baseline.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from .. import db
from ..agents import change, galileo, knowledge_desk, partner_desk, proposal, triage
from ..anonymise import Refused, anonymise_mail
from ..config import ROOT, get_settings
from ..db import Draft, Family, KnowledgeGap, Mail, PriceItem, TripRequest
from ..synth.generate import build

FIELDS = [("destination", "destination"), ("days", "days"), ("month", "month"), ("child_ages", "child_ages"),
          ("budget", "budget_eur")]


def pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def match(truth: dict, field: str, got) -> bool:
    if field in truth.get("accept", {}):
        return got in truth["accept"][field] or (isinstance(got, float) and int(got) in truth["accept"][field])
    want = truth.get(field)
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return float(want) == float(got)
    return want == got


def triage_report(mails: list[Mail]) -> dict:
    cat_ok = 0
    confusion = Counter()
    fields, fields_n = Counter(), 0
    dest_ok = dest_n = 0
    for m in mails:
        t, got = m.truth, m.triage or {}
        confusion[(t["category"], got.get("category"))] += 1
        cat_ok += t["category"] == got.get("category")
        if t["category"] in ("new_request", "question") and (t.get("destination") or "destination" in t.get("accept", {})):
            dest_n += 1
            dest_ok += match(t, "destination", got.get("destination"))
        if t["category"] == "new_request":
            fields_n += 1
            for ft, fg in FIELDS:
                fields[ft] += match(t, ft, got.get(fg))
    return {"mails": len(mails), "category_accuracy_pct": pct(cat_ok, len(mails)),
            "destination_accuracy_pct": pct(dest_ok, dest_n),
            "new_request_fields_pct": {k: pct(v, fields_n) for k, v in fields.items()},
            "misclassified": sorted(f"{a} -> {b} ({n})" for (a, b), n in confusion.items() if a != b)}


def run(seed: int | None = None, out_dir: Path | None = None) -> dict:
    seed = seed if seed is not None else get_settings().seed
    build(seed)
    rep: dict = {"seed": seed, "model": get_settings().model}
    with db.session() as s:
        # Anonymiser first: it is the gate for real data -------------------------------------
        all_mails = list(s.scalars(select(Mail)).all())
        refused, leaks = [], 0
        for m in all_mails:
            f = s.get(Family, m.family_id) if m.family_id else None
            try:
                out, _ = anonymise_mail({"sender": m.sender, "subject": m.subject, "body": m.body},
                                        {"contact_name": f.contact_name, "surname": f.surname} if f else None)
                if f and any(p in out["body"] for p in f.contact_name.split() if len(p) > 2):
                    leaks += 1
            except Refused as e:
                refused.append(f"{m.id} ({', '.join(sorted({x.kind for x in e.result.residual}))})")
        rep["anonymiser"] = {"mails": len(all_mails), "passed": len(all_mails) - len(refused), "refused": refused,
                             "known_names_left_in_passed_mails": leaks}

        # Injection: 20 attack mails must all be flagged; ordinary mail must pass -----------------
        from ..guardrails import detect_injection
        from .sets import INJECTIONS, KNOWLEDGE_QUESTIONS
        flagged = sum(detect_injection("Hallo,\n\n" + t)["flagged"] for t in INJECTIONS)
        fp = [m.id for m in all_mails if detect_injection(f"{m.subject}\n{m.body}")["flagged"]]
        rep["injection"] = {"attack_mails": len(INJECTIONS), "flagged_pct": pct(flagged, len(INJECTIONS)),
                            "false_positive_pct": pct(len(fp), len(all_mails)), "false_positives": fp}

        # Knowledge retrieval: right snippet in the top 3, current policy version only -------------
        from ..knowledge.store import KnowledgeBase
        kb = KnowledgeBase(s)
        top3, misses, current, skipped = 0, [], 0, []
        from ..knowledge.store import searchable
        live = {i.id for i in s.scalars(searchable()).all()}
        asked = [x for x in KNOWLEDGE_QUESTIONS if x[1] in live]
        skipped = [x[1] for x in KNOWLEDGE_QUESTIONS if x[1] not in live]  # not approved: correctly not findable
        for q, want, role in asked:
            ids = [h.id for h in kb.search(q, k=3, role=role)]
            top3 += want in ids
            if want not in ids:
                misses.append(f"{q} -> {ids}")
            if want == "k-policy-payment":
                current += want in ids and "k-policy-payment-2025" not in ids
        rep["knowledge_retrieval"] = {"questions": len(asked), "skipped_not_approved": skipped, "top3_pct": pct(top3, len(asked)),
                                      "current_policy_pct": pct(current, 2), "misses": misses,
                                      "specialist_cannot_see_margins": not any(h.id == "k-policy-margins" for h in kb.search("marge afspraken hotels", k=5, role="specialist"))}

        # Price check: earlier offers recalculated by the calculation service, exact to the euro ----
        from ..pricing import calculate
        offers = s.scalars(select(Draft).where(Draft.kind == "proposal", Draft.status == "approved")).all()
        exact = 0
        for d in offers:
            tr = s.get(TripRequest, d.request_id)
            fam = s.get(Family, tr.family_id)
            again = calculate(s, tr.destination, d.data["route"], fam.adults, fam.child_ages,
                              [a for r in d.data["route"] for a in r.get("activities", [])]).sell
            exact += abs(again - d.data["price"]["sell_eur"]) < 0.5
        rep["price_check"] = {"offers": len(offers), "exact_pct": pct(exact, len(offers))}

        t0 = time.perf_counter()
        triage.triage_inbox(s)
        triage_ms = (time.perf_counter() - t0) * 1000 / max(len(all_mails), 1)
        mails = list(s.scalars(select(Mail)).all())
        clean = [m for m in mails if m.truth.get("set") != "hard"]
        hard = [m for m in mails if m.truth.get("set") == "hard"]
        rep["triage_clean"] = triage_report(clean) | {"avg_ms": round(triage_ms, 1)}
        rep["triage_hard"] = triage_report(hard)

        # Change agent ---------------------------------------------------------------------
        for name, subset in (("change_clean", clean), ("change_hard", hard)):
            ch = [m for m in subset if m.truth["category"] == "change"]
            linked = ops_ok = 0
            for m in ch:
                if (m.triage or {}).get("request_id") != m.truth["request_id"]:
                    continue
                linked += 1
                d = change.handle_change(s, m.id)
                got = [(o["op"], o["stop"], o["nights"]) for o in d.data["ops"]]
                ops_ok += got == [(o["op"], o["stop"], o["nights"]) for o in m.truth["ops"]]
            rep[name] = {"change_mails": len(ch), "linked_to_right_trip_pct": pct(linked, len(ch)),
                         "changes_understood_pct": pct(ops_ok, len(ch))}

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
        for name, subset in (("knowledge_clean", clean), ("knowledge_hard", hard)):
            qs = [m for m in subset if m.truth["category"] == "question"]
            right = answerable = gapped = unanswerable = wrong_confident = 0
            for m in qs:
                body = m.body.split("\n\n")
                res = knowledge_desk.ask(s, body[1] if len(body) > 1 else m.body, team_id=m.truth.get("team"), mail_id=m.id)
                if m.truth.get("knowledge_id"):
                    answerable += 1
                    right += m.truth["knowledge_id"] in res["cited"] and res["confident"]
                else:
                    unanswerable += 1
                    gapped += res["gap_id"] is not None
                    wrong_confident += bool(res["confident"])
            rep[name] = {"answerable": answerable, "answered_with_right_source_pct": pct(right, answerable),
                         "unanswerable": unanswerable, "became_gap_pct": pct(gapped, unanswerable),
                         "confident_but_should_not_be": wrong_confident}
        rep["knowledge_hard"]["open_gaps_total"] = s.query(KnowledgeGap).filter(KnowledgeGap.status == "open").count()

        # Partner desk and Galileo on a sample -----------------------------------------------
        sample = [r for r in reqs if r.days >= 10][:10]
        pr_ok = g_warn = g_cmds = 0
        for r in sample:
            d = s.scalars(select(Draft).where(Draft.request_id == r.id, Draft.kind == "proposal")).first()
            created = partner_desk.plan_partner_requests(s, r.id)
            pr_ok += len(created) == 1 + len(d.data["route"])
            g = galileo.write_commands(s, r.id)
            g_cmds += len(g.data["commands"])
            g_warn += sum("onbekend formaat" in w for w in g.data["warnings"])
        rep["partner_desk"] = {"sampled": len(sample), "right_number_of_requests_pct": pct(pr_ok, len(sample))}
        rep["galileo"] = {"sampled": len(sample), "commands": g_cmds, "format_warnings": g_warn}

    rep["gates"] = gates(rep)
    out_dir = out_dir or ROOT / "data" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    (out_dir / "report.md").write_text(to_markdown(rep))
    return rep


def gates(rep: dict) -> dict:
    """The thresholds from the architecture. A failed gate blocks the change in CI."""
    from .sets import GATES
    out = {}
    for key, limit in GATES.items():
        section, field = key.split(".", 1)
        is_max = field.endswith("_max")
        name = field.removesuffix("_max")
        src = {"known_names_left": "known_names_left_in_passed_mails", "false_positive_pct": "false_positive_pct",
               "unsafe_activities": "unsafe_activities"}.get(name, name)
        val = rep.get(section, {}).get(src)
        ok = val is not None and (val <= limit if is_max else val >= limit)
        out[key] = {"value": val, "limit": limit, "ok": ok}
    return {"passed": all(g["ok"] for g in out.values()), "checks": out}


def to_markdown(rep: dict) -> str:
    lines = ["# Test bench report", "", f"Model: `{rep['model']}` · seed {rep['seed']} · synthetic data", ""]
    for section, v in rep.items():
        if not isinstance(v, dict):
            continue
        lines.append(f"## {section.replace('_', ' ').title()}")
        for k, x in v.items():
            lines.append(f"- {k.replace('_', ' ')}: {x}")
        lines.append("")
    return "\n".join(lines)
