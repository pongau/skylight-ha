"""Pure helpers for per-member chore summaries.

No Home Assistant imports — standard library only — so this module is unit
testable with a bare Python interpreter. The Home Assistant entity in
``sensor.py`` is a thin wrapper over ``build_member_summary``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def fmt_time(start_time: str | None) -> str | None:
    """Render a Skylight chore time as a 12-hour string, e.g. '20:00' -> '8:00 PM'.

    Accepts 'HH:MM', 'HH:MM:SS', or a full ISO datetime. Returns None when
    absent; passes unparseable input through unchanged.
    """
    if not start_time:
        return None
    text = str(start_time).strip()
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%I:%M %p").lstrip("0")
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return text


def _attrs(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("attributes", {}) if isinstance(item, dict) else {}


def category_id(chore: dict[str, Any]) -> str | None:
    """The assigned profile/category id for a chore, or None."""
    rel = chore.get("relationships", {}) if isinstance(chore, dict) else {}
    data = (rel.get("category") or {}).get("data") if isinstance(rel, dict) else None
    if isinstance(data, dict) and data.get("id") is not None:
        return str(data["id"])
    attr = _attrs(chore)
    if attr.get("category_id") is not None:
        return str(attr["category_id"])
    return None


def is_on_date(value: str | None, day: date) -> bool:
    """True if an ISO date/datetime string falls on ``day`` (date portion only)."""
    if not value:
        return False
    try:
        return date.fromisoformat(str(value)[:10]) == day
    except ValueError:
        return False
