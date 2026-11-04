"""Append-only, hash-chained audit log of human decisions.

Each entry stores the hash of the previous one, so changing or deleting any past entry breaks the chain
from that point on, and verify() shows where. Entries hold pseudonymous ids and references, never names
or mail text: the draft itself is represented by a hash of its body.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import AuditEntry, now

GENESIS = "0" * 64


def _digest(e: AuditEntry) -> str:
    payload = json.dumps({"at": e.at.isoformat(), "actor": e.actor, "action": e.action, "object_type": e.object_type,
                          "object_id": e.object_id, "ref": e.ref, "input_hash": e.input_hash, "prev": e.prev_hash},
                         sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def body_hash(text: str | None) -> str | None:
    return hashlib.sha256(text.encode()).hexdigest()[:32] if text is not None else None


def append(s: Session, actor: str, action: str, object_type: str, object_id, ref: str | None = None,
           content: str | None = None) -> AuditEntry:
    """Append one entry. With several writers at once, the unique prev_hash makes all but one fail; they retry
    on the new head, so the chain stays one line."""
    from sqlalchemy.exc import IntegrityError
    for attempt in range(20):
        last = s.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1)).first()
        e = AuditEntry(at=now(), actor=actor, action=action, object_type=object_type, object_id=str(object_id), ref=ref,
                       input_hash=body_hash(content), prev_hash=last.hash if last else GENESIS, hash="")
        e.hash = _digest(e)
        try:
            with s.begin_nested():
                s.add(e)
            return e
        except IntegrityError:
            import time
            time.sleep(0.01 * (attempt + 1))
    raise RuntimeError("Audit chain is busy; try again")


def verify(s: Session) -> dict:
    prev = GENESIS
    n = 0
    for e in s.scalars(select(AuditEntry).order_by(AuditEntry.id)).all():
        n += 1
        if e.prev_hash != prev or _digest(e) != e.hash:
            return {"ok": False, "entries": n, "broken_at": e.id}
        prev = e.hash
    return {"ok": True, "entries": n, "broken_at": None, "head": prev[:16]}



CHECKPOINT = "audit_checkpoint"


def verify_recent(s: Session) -> dict:
    """Check only what was added since the last check, continuing from a remembered point. Cheap enough for every
    15 minutes however long the log gets. The nightly full check (verify) also catches a change to an old entry."""
    from .db import Setting
    cp = (s.get(Setting, CHECKPOINT) or Setting(key=CHECKPOINT, value=None)).value or {}
    last_id, prev = cp.get("id", 0), cp.get("hash", GENESIS)
    if last_id:
        anchor = s.get(AuditEntry, last_id)
        if anchor is None or anchor.hash != prev:
            return {"ok": False, "entries": 0, "broken_at": last_id, "checked": "since checkpoint"}
    n = 0
    for e in s.scalars(select(AuditEntry).where(AuditEntry.id > last_id).order_by(AuditEntry.id)).all():
        n += 1
        if e.prev_hash != prev or _digest(e) != e.hash:
            return {"ok": False, "entries": n, "broken_at": e.id, "checked": "since checkpoint"}
        prev, last_id = e.hash, e.id
    if n:
        st = s.get(Setting, CHECKPOINT)
        value = {"id": last_id, "hash": prev}
        if st:
            st.value = value
        else:
            s.add(Setting(key=CHECKPOINT, value=value))
        s.commit()
    return {"ok": True, "entries": n, "broken_at": None, "checked": "since checkpoint", "head": prev[:16]}


def verify_full_and_remember(s: Session) -> dict:
    """Nightly: the whole log, and the result kept for the maintenance screen."""
    from .db import Setting
    from .clock import utcnow
    r = verify(s)
    s.merge(Setting(key="audit_full_check", value=r | {"at": utcnow().isoformat(timespec="minutes")}))
    s.commit()
    return r
