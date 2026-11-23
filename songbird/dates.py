"""A day as a person reads it, the American way: "September 30, 2026", "Wednesday, September 30, 2026".

The names are spelled out here rather than asked of strftime, whose %A and %B follow the machine's locale.
Days kept for a machine to read (a record, an edit, a file's name) stay ISO (2026-09-30).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def local_day(stamp: str | None) -> str:
    """The day a record's moment fell on where it is read (ISO, 2026-11-22), from its timestamp: a day given as
    a day (noon UTC, as --date and the studio's days are kept) is that day; any other moment, the local day it
    was then, so a version sung at 9 in the evening in California says it was sung that day, not the next."""
    text = str(stamp or "")
    if len(text) <= 10 or "T" not in text:
        return text[:10]
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if moment.tzinfo is None:
        return text[:10]
    utc = moment.astimezone(timezone.utc)
    if (utc.hour, utc.minute, utc.second, utc.microsecond) == (12, 0, 0, 0):
        return utc.date().isoformat()
    return moment.astimezone().date().isoformat()


def _day(day: str | date) -> date:
    return day if isinstance(day, date) else date.fromisoformat(local_day(str(day)))


def us_date(day: str | date) -> str:
    """'September 30, 2026' from '2026-09-30' (or a date, or an ISO timestamp)."""
    d = _day(day)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def long_date(day: str | date) -> str:
    """'Wednesday, September 30, 2026'."""
    d = _day(day)
    return f"{WEEKDAYS[d.weekday()]}, {us_date(d)}"
