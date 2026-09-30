"""A day as a person reads it, the American way: "September 30, 2026", "Wednesday, September 30, 2026".

The names are spelled out here rather than asked of strftime, whose %A and %B follow the machine's locale.
Days kept for a machine to read (a record, an edit, a file's name) stay ISO (2026-09-30).
"""
from __future__ import annotations

from datetime import date

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _day(day: str | date) -> date:
    return day if isinstance(day, date) else date.fromisoformat(str(day)[:10])


def us_date(day: str | date) -> str:
    """'September 30, 2026' from '2026-09-30' (or a date, or an ISO timestamp)."""
    d = _day(day)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def long_date(day: str | date) -> str:
    """'Wednesday, September 30, 2026'."""
    d = _day(day)
    return f"{WEEKDAYS[d.weekday()]}, {us_date(d)}"
