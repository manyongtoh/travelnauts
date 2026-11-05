"""Automatic send, earned per person and per kind of mail.

After ten drafts of one kind approved in a row without a change, the brain asks the person whether it may send
that kind by itself from now on. If they say yes, every new draft of that kind waits HOLD seconds (10), shown on
screen with a Stop button, and is then sent with every check that a manual approval has. A blocked check, a stop,
or a family mail that makes the draft stale leaves it waiting for the person as before.

Only low-risk kinds qualify: follow-ups, extras offers and partner requests and reminders. Proposals, changes,
answers, complaint replies, alternatives, roadbooks and anything with money stay manual, always.

Customer kinds belong to the trip's specialist. Partner kinds belong to the back office desk as a whole: any
back office colleague's approvals count, the question goes to whoever makes the tenth, and the answer counts for
the desk. Every question, answer, switch and stop is written to the audit chain.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import autonomy
from .clock import utcnow
from .db import Draft, Employee, Setting, TripRequest

ELIGIBLE = tuple(k for k, lvl in autonomy.KIND_CEILING.items() if lvl >= autonomy.ACT_AND_SAMPLE)
DESK_KINDS = ("partner_request", "partner_chase")
ASK_AFTER = 10
ASK_AGAIN_AFTER = 30  # after a "no", wait this many more unchanged approvals before asking once more
UNCHANGED = 0.02
DESK = "desk:back_office"


def hold_seconds() -> int:
    return max(5, int(os.getenv("BRAIN_AUTOSEND_HOLD", "10")))


def _key(owner: str, kind: str) -> str:
    return f"autosend:{owner}:{kind}"


def owner_of(s: Session, d: Draft) -> str | None:
    if d.kind in DESK_KINDS:
        return DESK
    tr = s.get(TripRequest, d.request_id) if d.request_id else None
    return (d.data or {}).get("specialist_id") or (tr.specialist_id if tr else None)


def state(s: Session, owner: str, kind: str) -> dict:
    st = s.get(Setting, _key(owner, kind))
    return dict(st.value) if st and st.value else {"status": "none", "streak": 0}


def _save(s: Session, owner: str, kind: str, value: dict) -> None:
    s.merge(Setting(key=_key(owner, kind), value=value, updated_at=utcnow()))


def record(s: Session, d: Draft, actor_id: str, approved: bool) -> dict | None:
    """Called after a person approves or rejects a draft. Returns the question to ask, if it is time."""
    from . import auditchain
    if d.kind not in ELIGIBLE or actor_id.startswith("auto:") or not autonomy.may_act_alone(d.kind):
        return None
    owner = owner_of(s, d)
    if not owner or (owner != DESK and owner != actor_id):
        return None  # a team lead deciding someone else's draft does not earn trust for them
    st = state(s, owner, d.kind)
    unchanged = approved and (d.edit_share or 0) < UNCHANGED
    st["streak"] = st.get("streak", 0) + 1 if unchanged else 0
    need = ASK_AGAIN_AFTER if st["status"] == "declined" else ASK_AFTER
    ask = None
    if st["status"] in ("none", "declined", "off") and st["streak"] >= need:
        st |= {"status": "asked", "asked_at": utcnow().isoformat(), "asked_of": actor_id}
        auditchain.append(s, "brain", "autosend_asked", "autosend", f"{owner}:{d.kind}", ref=actor_id)
    if st["status"] == "asked" and st.get("asked_of") == actor_id:
        ask = question(d.kind, st["streak"])
    _save(s, owner, d.kind, st)
    s.commit()
    return ask


LABEL = {"followup": "follow-ups", "extras": "extras offers", "partner_request": "partner requests", "partner_chase": "partner reminders"}


def question(kind: str, streak: int) -> dict:
    return {"kind": kind, "label": LABEL[kind], "streak": streak, "hold_seconds": hold_seconds(),
            "text": f"You sent the last {streak} {LABEL[kind]} without changing a word. Send them automatically from now on? "
                    f"Each one waits {hold_seconds()} seconds on screen with a Stop button first, and every check still applies."}


def owners_for(user_id: str, roles: set[str]) -> list[str]:
    return [user_id] + ([DESK] if "back_office" in roles else [])


def mine(s: Session, user_id: str, roles: set[str]) -> list[dict]:
    out = []
    for owner in owners_for(user_id, roles):
        for kind in ELIGIBLE:
            if (owner == DESK) != (kind in DESK_KINDS):
                continue
            st = state(s, owner, kind)
            if st["status"] != "none" or st.get("streak"):
                ask = st["status"] == "asked" and (owner == user_id or st.get("asked_of") == user_id)
                out.append({"kind": kind, "label": LABEL[kind], "owner": "desk" if owner == DESK else "me",
                            "status": st["status"], "streak": st.get("streak", 0), "ask": question(kind, st["streak"]) if ask else None})
    return out


def answer(s: Session, user_id: str, roles: set[str], kind: str, choice: str) -> dict:
    """choice: yes | no | off."""
    from . import auditchain
    if kind not in ELIGIBLE or choice not in ("yes", "no", "off"):
        raise ValueError("Unknown kind or choice")
    owner = DESK if kind in DESK_KINDS else user_id
    if owner == DESK and "back_office" not in roles:
        raise PermissionError("Partner mail belongs to the back office")
    st = state(s, owner, kind)
    if choice == "yes":
        if not (st["status"] == "asked" or (st["status"] == "off" and st.get("on_at"))):
            raise ValueError("Automatic send is offered after ten unchanged approvals in a row")
        st |= {"status": "on", "on_at": utcnow().replace(microsecond=0).isoformat(), "on_by": user_id}  # drafts carry whole seconds
    elif choice == "no":
        st |= {"status": "declined", "streak": 0}
    else:
        st |= {"status": "off", "streak": 0, "off_at": utcnow().isoformat()}
    _save(s, owner, kind, st)
    auditchain.append(s, user_id, f"autosend_{choice}", "autosend", f"{owner}:{kind}")
    s.commit()
    return st


def send_at(s: Session, d: Draft, cache: dict | None = None) -> datetime | None:
    """When this draft goes out by itself, or None when it waits for a person."""
    if d.status != "draft" or d.kind not in ELIGIBLE or not autonomy.may_act_alone(d.kind):
        return None
    x = d.data or {}
    if x.get("auto_stopped") or x.get("auto_blocked"):
        return None
    owner = owner_of(s, d)
    if not owner:
        return None
    cache = {} if cache is None else cache
    st = cache.get((owner, d.kind)) or cache.setdefault((owner, d.kind), state(s, owner, d.kind))
    if st["status"] != "on" or not st.get("on_at") or d.created_at < datetime.fromisoformat(st["on_at"]):
        return None  # only drafts made after the switch; older ones were never on anyone's countdown
    return d.created_at + timedelta(seconds=hold_seconds())


def stop(s: Session, d: Draft, user_id: str) -> Draft:
    from . import auditchain
    if d.status != "draft":
        raise ValueError(f"Too late: the draft is already {d.status}")
    d.data = (d.data or {}) | {"auto_stopped": user_id, "auto_stopped_at": utcnow().isoformat()}
    auditchain.append(s, user_id, "autosend_stop", f"draft:{d.kind}", d.id, ref=d.request_id)
    s.commit()
    return d


def send(s: Session, d: Draft) -> bool:
    from .workflow import BlockedByCheck, approve_draft
    owner = owner_of(s, d)
    st = state(s, owner, d.kind)
    who = st.get("on_by") or owner
    emp = s.get(Employee, who)
    # claim the row first, so two workers never send the same draft twice (the lock holds until commit)
    claimed = s.execute(update(Draft).where(Draft.id == d.id, Draft.status == "draft").values(status="sending")).rowcount
    if claimed != 1:
        s.rollback()
        return False
    s.execute(update(Draft).where(Draft.id == d.id).values(status="draft"))
    s.expire(d)
    try:
        s.execute(update(Draft).where(Draft.id == d.id).values(autonomy_level=autonomy.ACT_AND_SAMPLE))
        approve_draft(s, d.id, f"auto: {emp.name if emp else who}", actor_id=f"auto:{who}")
        return True
    except (BlockedByCheck, ValueError) as e:
        s.rollback()
        d = s.get(Draft, d.id)
        if d.status == "draft":
            d.data = (d.data or {}) | {"auto_blocked": str(e)[:300]}
            s.commit()
        return False


def run_due(s: Session, now: datetime | None = None) -> dict:
    """Send every draft whose hold has passed. Runs with every worker tick (15 seconds)."""
    now = now or utcnow()
    since = now - timedelta(days=2)
    cache, sent, blocked = {}, 0, 0
    for d in s.scalars(select(Draft).where(Draft.status == "draft", Draft.kind.in_(ELIGIBLE), Draft.created_at >= since)).all():
        at = send_at(s, d, cache)
        if at and at <= now:
            if send(s, d):
                sent += 1
            else:
                blocked += 1
    return {"sent": sent, "blocked": blocked}
