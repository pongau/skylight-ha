"""Pure helpers for the Skylight calendar platform (no Home Assistant imports).

Kept HA-free so it can be unit tested with a bare Python interpreter.
"""

from __future__ import annotations

from typing import Any


def clean_rrule(value: Any) -> str | None:
    """Extract the single RRULE string Home Assistant expects.

    Skylight returns ``rrule`` as a list of RFC 5545 content lines, e.g.
    ``['EXDATE;TZID=...:...', 'RRULE:FREQ=WEEKLY']``. Home Assistant's
    ``CalendarEvent.rrule`` wants just the rule, *without* the ``RRULE:`` prefix
    (e.g. ``'FREQ=WEEKLY'``) — a single string, or ``None``.

    EXDATE and other lines are dropped: ``CalendarEvent`` has no field for them,
    and Skylight already returns pre-expanded occurrences, so the exclusions are
    not needed for display.
    """
    if value is None:
        return None
    lines = value if isinstance(value, (list, tuple)) else [value]
    for line in lines:
        if not isinstance(line, str):
            continue
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("RRULE:"):
            return stripped[len("RRULE:"):].strip() or None
        if upper.startswith("FREQ="):
            return stripped or None
    return None
