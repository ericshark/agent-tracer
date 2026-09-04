from datetime import UTC, datetime


def as_utc(dt: datetime | None) -> datetime | None:
    """Normalize to aware-UTC.

    PostgreSQL returns aware datetimes for timestamptz; SQLite (used in tests)
    returns naive ones. Naive values are treated as UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
