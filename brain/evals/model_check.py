"""A smaller bench for a real model on slow hardware (test #1): `brain modelcheck`.

The full bench sends every mail through the model, which takes hours on a machine without a GPU. This takes a
stratified sample (clean, hard and English mail; a few proposals, complaints and partner replies), scores it the
same way, and keeps sample texts so a person can read what the model actually writes.
Run in CI by .github/workflows/gemma.yml (Ollama with Gemma 4 on a GitHub runner, CPU only).
"""
from __future__ import annotations

import json
import random
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from .. import db
from ..config import ROOT
from ..db import Draft, Mail, ModelCall, PartnerRequest, TripRequest
from ..synth.generate import build
from .bench import pct, triage_report


def _time(fn, *a):
    t0 = time.perf_counter()
    try:
        return fn(*a), None, time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001  a failure is a result here, not a crash
        return None, f"{type(e).__name__}: {str(e)[:160]}", time.perf_counter() - t0


def run(mails: int = 30, proposals: int = 4, complaints: int = 3, replies: int = 4, seed: int = 42) -> dict:
    import os
    from ..agents import partner_desk, proposal, sales, triage
    build(seed, n_families=80, hard=True)
    rng = random.Random(seed)
    rep: dict = {"model_small": os.getenv("BRAIN_MODEL_SMALL") or os.getenv("BRAIN_MODEL", "sandbox"),
                 "model_large": os.getenv("BRAIN_MODEL_LARGE") or os.getenv("BRAIN_MODEL", "sandbox"), "errors": []}
    with db.session() as s:
        everything = list(s.scalars(select(Mail).where(Mail.status == "new")).all())
        by_set = {k: [m for m in everything if m.truth.get("set", "clean") == k and m.truth.get("category")] for k in ("clean", "hard", "english")}
        n = {"clean": mails // 2, "hard": mails // 4, "english": mails - mails // 2 - mails // 4}
        sample = []
        for k, pool in by_set.items():  # spread over categories
            cats = {}
            for m in pool:
                cats.setdefault(m.truth["category"], []).append(m)
            picked = []
            while len(picked) < min(n[k], len(pool)):
                for c in sorted(cats):
                    if cats[c] and len(picked) < n[k]:
                        picked.append(cats[c].pop(rng.randrange(len(cats[c]))))
            sample += picked
        secs = []
        for m in sample:
            _, err, t = _time(triage.triage_mail, s, m.id)
            secs.append(t)
            if err:
                rep["errors"].append({"step": "triage", "mail": m.id, "error": err})
                s.rollback()
        s.expire_all()
        got = [s.get(Mail, m.id) for m in sample]
        for k in ("clean", "hard", "english"):
            part = [m for m in got if m.truth.get("set", "clean") == k and m.triage]
            rep[f"triage_{k}"] = triage_report(part) if part else {"mails": 0}
        rep["triage_seconds_avg"] = round(sum(secs) / max(len(secs), 1), 1)
        rep["triage_failed"] = sum(1 for e in rep["errors"] if e["step"] == "triage")

        # proposals: the writing that matters most
        reqs = s.scalars(select(TripRequest).where(TripRequest.status == "new").order_by(TripRequest.id)).all()[:proposals]
        texts, problems, psecs = [], 0, []
        for tr in reqs:
            d, err, t = _time(proposal.write_proposal, s, tr.id)
            psecs.append(t)
            if err:
                rep["errors"].append({"step": "proposal", "request": tr.id, "error": err})
                s.rollback()
                continue
            problems += bool(d.data.get("problems"))
            texts.append({"request": tr.id, "price_eur": d.data["price"]["sell_eur"], "problems": d.data.get("problems"), "text": d.body})
        rep["proposals"] = {"written": len(texts), "of": len(reqs), "with_problems": problems,
                            "seconds_avg": round(sum(psecs) / max(len(psecs), 1), 1)}
        rep["proposal_samples"] = texts[:3]

        # complaints: never promise money
        from ..agents.sales import MONEY
        cm = [m for m in s.scalars(select(Mail).where(Mail.family_id.is_not(None))).all()
              if (m.truth or {}).get("category") == "complaint"][:complaints]
        ctexts = []
        for m in cm:
            d, err, _ = _time(sales.complaint, s, m.id)
            if err:
                rep["errors"].append({"step": "complaint", "mail": m.id, "error": err})
                s.rollback()
                continue
            ctexts.append({"mail": m.id, "money_promise": any(w in d.body.lower() for w in MONEY), "text": d.body})
        rep["complaints"] = {"written": len(ctexts), "of": len(cm), "money_promises": sum(c["money_promise"] for c in ctexts)}
        rep["complaint_samples"] = ctexts[:2]

        # partner replies with an offer in a PDF
        pm = [m for m in s.scalars(select(Mail).where(Mail.partner_id.is_not(None))).all()
              if m.attachments and "price_eur" in (m.truth or {})][:replies]
        ok = 0
        for m in pm:
            m.status = "triaged"
            s.commit()
            _, err, _ = _time(partner_desk.read_reply, s, m.id)
            if err:
                rep["errors"].append({"step": "partner_reply", "mail": m.id, "error": err})
                s.rollback()
                continue
            pr = s.get(PartnerRequest, m.truth["partner_request_id"])
            ok += (pr.status == "answered" and abs(((pr.offer or {}).get("price_eur") or 0) - m.truth["price_eur"]) < 1) \
                if m.truth["available"] else pr.status == "declined"
        rep["partner_replies"] = {"read": len(pm), "right": ok, "right_pct": pct(ok, len(pm))}

        calls = s.scalars(select(ModelCall)).all()
        real = [c for c in calls if c.model != "sandbox"]
        rep["model_calls"] = {"total": len(calls), "real_model": len(real), "failed": sum(not c.ok for c in real),
                              "fell_back_to_stand_in": sum(c.model == "sandbox" for c in calls),
                              "by_task": dict(Counter(c.task for c in real)),
                              "tokens_per_second": round(sum(c.tokens_out for c in real if c.ok) /
                                                         max(sum(c.ms for c in real if c.ok) / 1000, 0.001), 1)}
    return rep


def where() -> str:
    import os
    base = os.getenv("BRAIN_MODEL_BASE_URL", "")
    return "local Ollama, CPU only" if "localhost" in base or "127.0.0.1" in base else f"hosted at {base.split('/')[2] if '//' in base else base}"


def to_markdown(r: dict) -> str:
    t = lambda k: r.get(k, {})  # noqa: E731
    lines = [f"# Model check: {r['model_small']} (small) / {r['model_large']} (large)", "",
             f"A sample of the bench ({where()}). Synthetic data. Compare with the stand-in in docs/test-reports.", "",
             "| Check | Result |", "|---|---|"]
    for k in ("clean", "hard", "english"):
        x = t(f"triage_{k}")
        lines.append(f"| Triage, {k} mail ({x.get('mails', 0)}) | category {x.get('category_accuracy_pct')}%, destination "
                     f"{x.get('destination_accuracy_pct')}% |")
    lines += [f"| Triage failures | {r['triage_failed']} |", f"| Seconds per mail | {r['triage_seconds_avg']} |",
              f"| Proposals written | {t('proposals').get('written')} of {t('proposals').get('of')}, "
              f"{t('proposals').get('with_problems')} flagged by the checks, {t('proposals').get('seconds_avg')} s each |",
              f"| Complaint replies | {t('complaints').get('written')} of {t('complaints').get('of')}, "
              f"money promises: {t('complaints').get('money_promises')} |",
              f"| Partner offers in PDF read right | {t('partner_replies').get('right')} of {t('partner_replies').get('read')} |",
              f"| Model calls | {t('model_calls').get('real_model')} to the model, {t('model_calls').get('failed')} failed, "
              f"{t('model_calls').get('fell_back_to_stand_in')} fell back to the stand-in |",
              f"| Speed | {t('model_calls').get('tokens_per_second')} tokens per second |", ""]
    for k in ("clean", "hard", "english"):
        mis = t(f"triage_{k}").get("misclassified")
        if mis:
            lines.append(f"Misclassified ({k}): {', '.join(mis)}")
        miss = t(f"triage_{k}").get("destination_missed")
        if miss:
            lines.append(f"Destination missed ({k}): {'; '.join(miss)}")
    if r["errors"]:
        lines += ["", "## Errors", ""] + [f"- {e['step']} {e.get('mail') or e.get('request')}: {e['error']}" for e in r["errors"][:15]]
    for p in r.get("proposal_samples", []):
        lines += ["", f"## Proposal {p['request']} (calculated price {p['price_eur']} euro)",
                  f"Checks: {', '.join(p['problems']) if p['problems'] else 'no problems'}", "", "```", p["text"], "```"]
    for c in r.get("complaint_samples", []):
        lines += ["", f"## Complaint reply to {c['mail']}", "", "```", c["text"], "```"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="brain modelcheck")
    ap.add_argument("--mails", type=int, default=30)
    ap.add_argument("--proposals", type=int, default=4)
    ap.add_argument("--complaints", type=int, default=3)
    ap.add_argument("--replies", type=int, default=4)
    a = ap.parse_args(argv)
    r = run(a.mails, a.proposals, a.complaints, a.replies)
    out = ROOT / "data" / "modelcheck"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(r, indent=2, default=str))
    (out / "report.md").write_text(to_markdown(r))
    print(to_markdown(r))


if __name__ == "__main__":
    main()
