"""One clock for the whole platform: naive datetimes in UTC (the database convention), without the deprecated
datetime.utcnow(). Screens convert to Amsterdam time when they show a time.

The operations simulation moves this clock forward (set_now) to run two weeks in minutes. Nothing else may.
"""
from datetime import date, datetime, timedelta, timezone

_offset = timedelta(0)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + _offset


def today() -> date:
    return utcnow().date()


def set_now(when: datetime) -> None:
    global _offset
    _offset = when - datetime.now(timezone.utc).replace(tzinfo=None)


def reset() -> None:
    global _offset
    _offset = timedelta(0)
