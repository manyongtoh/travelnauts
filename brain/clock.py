"""One clock for the whole platform: naive datetimes in UTC (the database convention), without the deprecated
datetime.utcnow(). Screens convert to Amsterdam time when they show a time."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
