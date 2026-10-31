"""A single source of truth for the current time.

Timestamps are stored as *naive* datetimes that always represent UTC.
PostgreSQL and SQLite disagree about how they hand timezone-aware values
back, so keeping one convention everywhere means a comparison behaves the
same in production and in the test suite.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time without a timezone attached."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
