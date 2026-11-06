"""One clock for the whole platform: naive datetimes in UTC (the database convention), without the deprecated
datetime.utcnow(). Screens convert to Amsterdam time when they show a time.

The operations simulation moves this clock forward (set_now) to run two weeks in minutes. Nothing else may.
"""
from datetime import UTC, date, datetime, timedelta

_offset = timedelta(0)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) + _offset


def today() -> date:
    return utcnow().date()


def set_now(when: datetime) -> None:
    global _offset
    _offset = when - datetime.now(UTC).replace(tzinfo=None)


def reset() -> None:
    global _offset
    _offset = timedelta(0)


DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MONTHS_NL = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
             "november", "december"]


def nl_date(d) -> str:
    """A date the way a family reads it in a Dutch mail: dinsdag 10 november (the year only when it is not this year)."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    s = f"{DAYS_NL[d.weekday()]} {d.day} {MONTHS_NL[d.month - 1]}"
    return s if d.year == today().year else f"{s} {d.year}"
