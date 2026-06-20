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
