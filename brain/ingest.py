"""Load an export from TravelSpirit for the anonymised stage.

Input: a JSON Lines file, one object per line:
  {"type": "relation", "id": "...", "contact_name": "...", "surname": "...", "adults": 2, "child_ages": [6, 9], ...}
  {"type": "mail", "id": "...", "relation_id": "...", "received_at": "2026-11-01T09:12:00", "sender": "...",
   "subject": "...", "body": "..."}

Every record goes through the anonymiser. Refused records are not loaded; only their id and the
reason are written to the report (never their content), so a person can look them up in TravelSpirit.
Requires BRAIN_DATA_STAGE=anonymised.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from . import db
from .anonymise import Refused, anonymise_mail, anonymise_relation
from .config import get_settings
from .db import Family, Mail
from .tenant import tenant


def ref_for(source_id: str) -> str:
    """Stable, one way reference, so the same relation maps to the same anonymous family."""
    return "anon-" + hashlib.sha256(f"{tenant().tenant_id}:{source_id}".encode()).hexdigest()[:10]


def ingest(path: Path | str) -> dict:
    if get_settings().data_stage != "anonymised":
        raise RuntimeError("Set BRAIN_DATA_STAGE=anonymised to load real (anonymised) data")
    lines = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    relations = {r["id"]: r for r in lines if r.get("type") == "relation"}
    report = {"relations": 0, "mails": 0, "refused": [], "removed": {}}
    with db.session() as s:
        for rid, rel in relations.items():
            ref = ref_for(rid)
            if not s.get(Family, ref):
                s.add(Family(**anonymise_relation(rel, ref), synthetic=False))
                report["relations"] += 1
        for m in (r for r in lines if r.get("type") == "mail"):
            rel = relations.get(m.get("relation_id"))
            try:
                am, rep = anonymise_mail(m, rel)
            except Refused as e:
                report["refused"].append({"id": m.get("id"), "reasons": sorted({f.kind for f in e.result.residual})})
                continue
            for k, v in rep["body"]["removed"].items():
                report["removed"][k] = report["removed"].get(k, 0) + v
            mid = ref_for("mail:" + str(m.get("id")))
            if s.get(Mail, mid):
                continue
            s.add(Mail(id=mid, received_at=datetime.fromisoformat(m["received_at"]), sender=am["sender_domain"],
                       subject=am["subject"], body=am["body"], family_id=ref_for(rel["id"]) if rel else None,
                       truth={}, synthetic=False))
            report["mails"] += 1
        s.commit()
    return report
