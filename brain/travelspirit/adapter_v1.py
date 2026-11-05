"""Adapter for TravelSpirit API v1 (read-only), behind the platform's own contract.

Agents never see TravelSpirit's format: this adapter turns TravelSpirit responses into the platform's
objects (mail, relation, dossier). A new API version gets its own adapter (adapter_v2.py) behind the same
functions; which one is used is a setting per environment.

The field names below are an ASSUMED shape, recorded in tests/contract/recorded/. Replace the recordings
with real TravelSpirit responses as soon as the client shares test access; the contract tests then show
exactly which mappings need to change. All ids go through id_map, so a change in TravelSpirit's ids after
the merger touches one place.
"""
from __future__ import annotations

from datetime import datetime


def id_map(ts_id: str | int, kind: str) -> str:
    return f"ts-{kind}-{ts_id}"


def to_mail(r: dict) -> dict:
    return {
        "id": id_map(r["MessageId"], "mail"),
        "received_at": datetime.fromisoformat(r["ReceivedDateTime"]).replace(tzinfo=None).isoformat(),
        "sender": r["From"]["Address"],
        "subject": r.get("Subject") or "",
        "body": r.get("BodyText") or "",
        "family_id": id_map(r["RelationId"], "relation") if r.get("RelationId") else None,
        "dossier_id": id_map(r["DossierId"], "dossier") if r.get("DossierId") else None,
    }


def to_relation(r: dict) -> dict:
    travellers = r.get("Travellers", [])
    adults = [t for t in travellers if t.get("Type") == "Adult"]
    children = [t for t in travellers if t.get("Type") == "Child"]
    return {
        "id": id_map(r["RelationId"], "relation"),
        "surname": r["LastName"],
        "contact_name": f"{r.get('FirstName', '')} {r['LastName']}".strip(),
        "email": r.get("Email"),
        "adults": len(adults) or 1,
        "child_ages": sorted(int(t["Age"]) for t in children if t.get("Age") is not None),
        "city": (r.get("Address") or {}).get("City"),
    }


def to_dossier(r: dict) -> dict:
    return {
        "id": id_map(r["DossierId"], "dossier"),
        "family_id": id_map(r["RelationId"], "relation"),
        "destination": (r.get("Destination") or "").lower().replace(" ", "-"),
        "days": int(r.get("DurationDays") or 0),
        "status": {"Quote": "proposal_sent", "Booked": "booked", "Cancelled": "lost", "New": "new"}.get(r.get("Status"), "new"),
        "depart_date": r.get("DepartureDate"),
    }
