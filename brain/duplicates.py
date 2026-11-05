"""Duplicate family records: find them, show the evidence, merge on a person's say-so.

Doubles come from TravelSpirit (the same family entered twice over the years) and from the brain itself (a
first mail from the other parent's address opens a new relation). Before go-live, and weekly after, this lists
likely pairs with the evidence for each. Nothing merges by itself: a wrong merge sends one family's mail to
another. On approval the brain moves trips, mail and addresses to the record that is kept and remembers the
other address; the merge in TravelSpirit is done by its administrator from the exported plan (the brain only
reads TravelSpirit). A pair a person marks as "keep apart" is never suggested again.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import utcnow
from .db import Draft, Family, FamilyAddress, Mail, Setting, TripRequest

PARTICLES = {"van", "de", "der", "den", "ter", "ten", "het", "'t", "la", "le", "du", "da"}
MERGED = "Samengevoegd met "
STRONG, MEDIUM = 3, 2
SHOW_FROM = 3


def _surname_key(s: str | None) -> str:
    words = [w for w in re.split(r"[\s-]+", (s or "").lower()) if w and w not in PARTICLES]
    return " ".join(words)


def merged_into(f: Family) -> str | None:
    return f.notes[len(MERGED):].split(" ", 1)[0] if (f.notes or "").startswith(MERGED) else None


def _apart(s: Session) -> set[frozenset]:
    st = s.get(Setting, "duplicates:apart")
    return {frozenset(p) for p in ((st.value if st else None) or [])}


def candidates(s: Session) -> list[dict]:
    from .agents.triage import normalise_address
    from .anonymise import FREEMAIL
    fams = [f for f in s.scalars(select(Family)).all() if not merged_into(f)]
    by_id = {f.id: f for f in fams}
    evidence: dict[frozenset, list[tuple[int, str]]] = defaultdict(list)

    def add(a, b, weight, why):
        if a != b and a in by_id and b in by_id:
            evidence[frozenset((a, b))].append((weight, why))

    addresses = defaultdict(set)
    for f in fams:
        if f.email:
            addresses[normalise_address(f.email)].add(f.id)
    for fa in s.scalars(select(FamilyAddress)).all():
        addresses[fa.email].add(fa.family_id)
    for addr, ids in addresses.items():
        for a, b in combinations(sorted(ids), 2):
            add(a, b, STRONG, f"same address {addr}")

    groups = defaultdict(list)  # compare only within a surname: never every family with every family
    for f in fams:
        if _surname_key(f.surname):
            groups[_surname_key(f.surname)].append(f)
    for _, fs in groups.items():
        for a, b in combinations(fs, 2):
            yrs_a, yrs_b = sorted(a.child_birth_years or []), sorted(b.child_birth_years or [])
            if yrs_a and yrs_a == yrs_b:
                add(a.id, b.id, STRONG, f"same surname and children born {', '.join(map(str, yrs_a))}")
            elif yrs_a and yrs_b and set(yrs_a) & set(yrs_b):
                add(a.id, b.id, MEDIUM, "same surname, some children born the same year")
            if a.city and b.city and a.city.lower() == b.city.lower():
                add(a.id, b.id, MEDIUM, f"same surname and city ({a.city})")
            if (a.contact_name or "").lower() == (b.contact_name or "").lower() and a.contact_name:
                add(a.id, b.id, MEDIUM, f"same contact name ({a.contact_name})")
            da = (a.email or "").rsplit("@", 1)[-1].lower()
            if da and da == (b.email or "").rsplit("@", 1)[-1].lower() and da not in FREEMAIL:
                add(a.id, b.id, MEDIUM, f"same surname and own mail domain ({da})")

    for m in s.scalars(select(Mail).where(Mail.family_id.like("f-new-%"))).all():
        for c in (m.triage or {}).get("possible_duplicate_of") or []:
            # a new relation is checked by a person anyway: show what it resembled, even on a surname alone
            add(m.family_id, c["family_id"], SHOW_FROM, "first mail looked like this family: " + ", ".join(c.get("why", [])))

    apart = _apart(s)
    trips = defaultdict(int)
    for (fid,) in s.execute(select(TripRequest.family_id)):
        trips[fid] += 1
    out = []
    for pair, ev in evidence.items():
        if pair in apart:
            continue
        seen, uniq = set(), []
        for w, why in sorted(ev, reverse=True):
            if why not in seen:
                seen.add(why)
                uniq.append((w, why))
        score = sum(w for w, _ in uniq)
        if score < SHOW_FROM:
            continue
        a, b = sorted((by_id[i] for i in pair), key=lambda f: (f.id.startswith("f-new-"), -trips[f.id], f.id))
        out.append({"keep": a.id, "drop": b.id, "score": score, "level": "likely" if score >= 5 else "possible",
                    "evidence": [w for _, w in uniq],
                    "keep_name": f"{a.contact_name} ({a.surname})", "drop_name": f"{b.contact_name} ({b.surname})",
                    "keep_trips": trips[a.id], "drop_trips": trips[b.id],
                    "keep_in_travelspirit": not a.id.startswith("f-new-"), "drop_in_travelspirit": not b.id.startswith("f-new-")})
    return sorted(out, key=lambda x: (-x["score"], x["keep"]))


def keep_apart(s: Session, a: str, b: str, by: str) -> None:
    from . import auditchain
    st = s.get(Setting, "duplicates:apart")
    pairs = list((st.value if st else None) or [])
    if sorted((a, b)) not in [sorted(p) for p in pairs]:
        pairs.append(sorted((a, b)))
    s.merge(Setting(key="duplicates:apart", value=pairs, updated_at=utcnow()))
    auditchain.append(s, by, "duplicates_keep_apart", "family", a, ref=b)
    s.commit()


def merge(s: Session, keep: str, drop: str, by: str) -> dict:
    """Move everything of `drop` to `keep`. The dropped record stays (TravelSpirit still has it until its
    administrator merges it there) but is marked, has no address, and is never matched again."""
    from . import auditchain
    from .agents.triage import normalise_address
    k, d = s.get(Family, keep), s.get(Family, drop)
    if k is None or d is None or keep == drop:
        raise ValueError("Pick two different families")
    if merged_into(k) or merged_into(d):
        raise ValueError("One of these was merged already")
    moved = {"trips": 0, "mails": 0, "addresses": 0, "drafts": 0}
    for t in s.scalars(select(TripRequest).where(TripRequest.family_id == drop)).all():
        t.family_id, moved["trips"] = keep, moved["trips"] + 1
    for m in s.scalars(select(Mail).where(Mail.family_id == drop)).all():
        m.family_id, moved["mails"] = keep, moved["mails"] + 1
    for fa in s.scalars(select(FamilyAddress).where(FamilyAddress.family_id == drop)).all():
        fa.family_id, moved["addresses"] = keep, moved["addresses"] + 1
    addr = normalise_address(d.email)
    if addr and addr != normalise_address(k.email) and s.get(FamilyAddress, addr) is None:
        s.add(FamilyAddress(email=addr, family_id=keep, added_by=by))  # their mail keeps finding them
        moved["addresses"] += 1
    for dr in s.scalars(select(Draft)).all():
        if (dr.data or {}).get("family_id") == drop:
            dr.data, moved["drafts"] = dr.data | {"family_id": keep}, moved["drafts"] + 1
    if not k.child_birth_years and d.child_birth_years:
        k.child_birth_years, k.child_ages = list(d.child_birth_years), list(d.child_ages or [])
    k.past_destinations = sorted(set(k.past_destinations or []) | set(d.past_destinations or []))
    k.notes = ((k.notes or "") + f"\nSamengevoegd: {drop} ({d.contact_name}) op {utcnow():%Y-%m-%d}.").strip()
    d.notes = f"{MERGED}{keep} door {by} op {utcnow():%Y-%m-%d}. " + (d.notes or "")
    d.email = None
    auditchain.append(s, by, "duplicates_merge", "family", keep, ref=drop)
    s.commit()
    return {"keep": keep, "drop": drop, "moved": moved}


def plan_csv(s: Session) -> str:
    """For the TravelSpirit administrator: which relations to merge there, and what the brain already did."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["keep_relation", "merge_relation", "status", "level", "evidence"])
    for f in s.scalars(select(Family)).all():
        if merged_into(f) and not f.id.startswith("f-new-"):
            w.writerow([merged_into(f), f.id, "merged in the brain: merge in TravelSpirit", "", ""])
    for c in candidates(s):
        if c["keep_in_travelspirit"] and c["drop_in_travelspirit"]:
            w.writerow([c["keep"], c["drop"], "to check", c["level"], "; ".join(c["evidence"])])
    return buf.getvalue()
