"""The two contracts between the brain and a company's own systems.

SystemOfRecord: where customers and trips live (TravelSpirit at the first client). The brain reads it and,
where allowed, writes drafts into it; it never keeps a second copy as the truth.
Channel: where messages come in and drafts go back for a person to send (TravelSpirit Mail at the first client;
WhatsApp or a web chat later).

Agents never call a system directly: they go through the tool server, which asks for these two. Which adapter
is used is a setting per environment (BRAIN_TRAVELSPIRIT=fake today); a client repo can bring its own adapters.

Write rule, for every adapter: agents only create drafts. A person always sends or confirms.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session


class SystemUnavailable(ConnectionError):
    """The system of record or the channel did not answer. Jobs wait and try again; nothing is lost."""


@runtime_checkable
class SystemOfRecord(Protocol):
    def customer(self, customer_id: str) -> dict: ...
    def trips(self, status: str | None = None) -> list[dict]: ...
    def draft_itinerary(self, request_id: str, plan: dict) -> dict: ...


@runtime_checkable
class Channel(Protocol):
    def inbox(self, status: str | None = "new") -> list[dict]: ...
    def message(self, message_id: str) -> dict: ...


def get_system_of_record(s: Session) -> SystemOfRecord:
    from .travelspirit.client import connect
    return connect(s, "record")


def get_channel(s: Session) -> Channel:
    from .travelspirit.client import connect
    return connect(s, "channel")
