"""TravelSpirit connection.

Today TravelSpirit's API is read-only; a two-way API is expected in January 2027.
The agents only talk to this interface, so swapping the fake for the real API touches one file.

Write rule: agents can only create *drafts* (a draft reisplan in the Visual Tour Builder,
a draft mail). A person always sends or confirms. With BRAIN_TRAVELSPIRIT_WRITE=off even
drafts are kept inside the brain only.
"""
from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import Draft, Family, Mail, TripRequest, as_dict


class TravelSpirit(Protocol):
    def inbox(self, status: str | None = "new") -> list[dict]: ...
    def mail(self, mail_id: str) -> dict: ...
    def relation(self, family_id: str) -> dict: ...
    def trips(self, status: str | None = None) -> list[dict]: ...
    def draft_reisplan(self, request_id: str, plan: dict) -> dict: ...


class FakeTravelSpirit:
    """Serves the synthetic data in the shape we expect from the real API."""

    def __init__(self, s: Session):
        self.s = s
        self.write_mode = get_settings().travelspirit_write

    def inbox(self, status: str | None = "new") -> list[dict]:
        q = select(Mail).order_by(Mail.received_at.desc())
        if status:
            q = q.where(Mail.status == status)
        return [self._mail(m) for m in self.s.scalars(q).all()]

    def mail(self, mail_id: str) -> dict:
        m = self.s.get(Mail, mail_id)
        if m is None:
            raise KeyError(mail_id)
        return self._mail(m)

    @staticmethod
    def _mail(m: Mail) -> dict:
        d = as_dict(m)
        d.pop("truth", None)  # ground truth is for the test bench only
        return d

    def relation(self, family_id: str) -> dict:
        f = self.s.get(Family, family_id)
        if f is None:
            raise KeyError(family_id)
        return as_dict(f)

    def trips(self, status: str | None = None) -> list[dict]:
        q = select(TripRequest)
        if status:
            q = q.where(TripRequest.status == status)
        return [as_dict(t) for t in self.s.scalars(q).all()]

    def draft_reisplan(self, request_id: str, plan: dict) -> dict:
        if self.write_mode == "off":
            return {"stored_in": "brain_only", "request_id": request_id}
        # In the fake, the "Visual Tour Builder draft" is a record we keep ourselves.
        return {"stored_in": "travelspirit_draft", "request_id": request_id, "vtb_draft_id": f"vtb-{request_id}",
                "days": len(plan.get("days", []))}


class RealTravelSpirit:  # pragma: no cover - needs API documentation and test access from Travelnauts
    def __init__(self, base_url: str, token: str):
        raise NotImplementedError(
            "Map the real TravelSpirit endpoints here once Travelnauts shares the API documentation and test access. "
            "Keep the same method names and return shapes as FakeTravelSpirit."
        )


def get_travelspirit(s: Session) -> TravelSpirit:
    mode = get_settings().travelspirit_mode
    if mode == "fake":
        return FakeTravelSpirit(s)
    raise NotImplementedError("Only the fake TravelSpirit is available in the sandbox")
