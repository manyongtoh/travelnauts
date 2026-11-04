"""The knowledge vault: markdown notes (Obsidian style) in git are the master for knowledge.

Each note has front matter (id, title, owner, review_by, roles, destination, topic, valid_from, valid_to)
and is split by "##" heading into chunks of at most a few hundred words. reindex() reads the vault and
updates the index in the database:
  * a new chunk arrives as "proposed" and waits for a person's approval;
  * a changed chunk goes back to "proposed" with a new version, so a change is always re-approved;
  * a policy note past its valid_to date is archived: kept for audits, never searched;
  * a chunk that disappeared from the vault is retired.
Approval state lives in the database, not in the notes, so writing in the vault cannot approve anything.

BRAIN_VAULT points at the vault (default: data/vault, filled by `brain seed` from the synthetic world).
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ROOT
from ..db import Employee, KnowledgeItem, Setting
from .store import clear_semantic_cache
from ..clock import utcnow

ALL_STAFF = ["specialist", "back_office", "team_lead", "content"]
MAX_WORDS = 300


def vault_dir() -> Path:
    return Path(os.getenv("BRAIN_VAULT", str(ROOT / "data" / "vault")))


def slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def parse_note(text: str) -> tuple[dict, str]:
    meta: dict = {}
    if text.startswith("---"):
        head, _, text = text[3:].partition("\n---")
        for line in head.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip()
                meta[k.strip()] = [x.strip() for x in v.strip("[]").split(",") if x.strip()] if v.startswith("[") else v
    return meta, text.strip()


def chunks(meta: dict, body: str) -> list[tuple[str, str, str]]:
    """(chunk_id_suffix, title, text). Splits by ## heading, then by size."""
    parts = re.split(r"(?m)^##\s+(.+)$", body)
    out = []
    intro = parts[0].strip()
    if intro:
        out.append(("", meta.get("title", ""), intro))
    for i in range(1, len(parts), 2):
        out.append((slug(parts[i]), parts[i].strip(), parts[i + 1].strip()))
    final = []
    for sid, title, text in out:
        words = text.split()
        for n in range(0, max(len(words), 1), MAX_WORDS):
            part = " ".join(words[n:n + MAX_WORDS])
            final.append((sid + (f"-{n // MAX_WORDS + 1}" if len(words) > MAX_WORDS else ""), title, part))
    return final


def write_note(path: Path, meta: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = "\n".join(f"{k}: [{', '.join(v)}]" if isinstance(v, list) else f"{k}: {v}" for k, v in meta.items() if v is not None)
    path.write_text(f"---\n{fm}\n---\n\n{body.strip()}\n", encoding="utf-8")


def export_from_db(s: Session, root: Path | None = None) -> int:
    """Write the synthetic knowledge as vault notes (used once by `brain seed`)."""
    root = root or vault_dir()
    n = 0
    for k in s.scalars(select(KnowledgeItem)).all():
        folder = k.destination or ("policy" if k.topic in ("policy", "house_voice") else "algemeen")
        meta = {"id": k.id, "title": k.title, "owner": k.owner_id, "review_by": k.review_by.isoformat(),
                "roles": k.roles or ALL_STAFF, "destination": k.destination, "topic": k.topic,
                "valid_from": k.valid_from.isoformat() if k.valid_from else None,
                "valid_to": k.valid_to.isoformat() if k.valid_to else None}
        write_note(root / folder / f"{slug(k.title)}.md", meta, k.body)
        k.source = f"{folder}/{slug(k.title)}.md"
        k.content_hash = hashlib.sha256(k.body.encode()).hexdigest()[:16]
        n += 1
    s.commit()
    return n


def reindex(s: Session, root: Path | None = None) -> dict:
    root = root or vault_dir()
    today = date.today()
    seen, added, changed, archived = set(), 0, 0, 0
    owners = {e.id for e in s.scalars(select(Employee)).all()}
    for path in sorted(root.rglob("*.md")):
        meta, body = parse_note(path.read_text(encoding="utf-8"))
        rel = str(path.relative_to(root))
        for sid, title, text in chunks(meta, body):
            cid = meta.get("id", slug(rel)) + (f"#{sid}" if sid else "")
            seen.add(cid)
            h = hashlib.sha256(text.encode()).hexdigest()[:16]
            vf = date.fromisoformat(meta["valid_from"]) if meta.get("valid_from") else None
            vt = date.fromisoformat(meta["valid_to"]) if meta.get("valid_to") else None
            item = s.get(KnowledgeItem, cid)
            owner = meta.get("owner") if meta.get("owner") in owners else next(iter(owners))
            fields = dict(title=title if sid else meta.get("title", title), body=text, destination=meta.get("destination"),
                          topic=meta.get("topic", "general"), owner_id=owner, roles=meta.get("roles") or ALL_STAFF,
                          review_by=date.fromisoformat(meta["review_by"]) if meta.get("review_by") else today,
                          source=rel + (f"#{sid}" if sid else ""), content_hash=h, valid_from=vf, valid_to=vt)
            if item is None:
                s.add(KnowledgeItem(id=cid, status="proposed", synthetic=True, **fields))
                s.flush()
                added += 1
            else:
                if item.content_hash and item.content_hash != h:
                    item.status, item.version, item.approved_by, item.approved_at = "proposed", item.version + 1, None, None
                    changed += 1
                for k, v in fields.items():
                    setattr(item, k, v)
            if vt and vt < today:
                it = s.get(KnowledgeItem, cid)
                if it.status != "archived":
                    it.status = "archived"
                    archived += 1
    retired = 0
    for item in s.scalars(select(KnowledgeItem).where(KnowledgeItem.source.is_not(None))).all():
        if item.id not in seen and item.status != "retired":
            item.status = "retired"
            retired += 1
    clear_semantic_cache(s)
    s.merge(Setting(key="last_reindex", value=utcnow().isoformat(timespec="minutes")))
    s.commit()
    return {"added": added, "changed": changed, "archived": archived, "retired": retired, "chunks": len(seen)}


def review_reminders(s: Session) -> dict:
    """Owners of knowledge past its review date get a reminder (listed on the team lead and content screens)."""
    due = s.scalars(select(KnowledgeItem).where(KnowledgeItem.status == "approved", KnowledgeItem.review_by < date.today())).all()
    by_owner: dict[str, list[str]] = {}
    for k in due:
        by_owner.setdefault(k.owner_id, []).append(k.id)
    s.merge(Setting(key="report:review_reminders", value={"at": utcnow().isoformat(timespec="minutes"), "owners": by_owner}))
    s.commit()
    return {"owners": len(by_owner), "items": len(due)}
