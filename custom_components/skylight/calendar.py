"""Calendar platform for Skylight (read-only)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SkylightConfigEntry
from .coordinator import SkylightCoordinator
from .entity import SkylightEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkylightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([SkylightCalendar(coordinator)])


class SkylightCalendar(SkylightEntity, CalendarEntity):
    """Exposes the Skylight frame's calendar events."""

    _attr_name = "Calendar"
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT
        | CalendarEntityFeature.DELETE_EVENT
        | CalendarEntityFeature.UPDATE_EVENT
    )

    def __init__(self, coordinator: SkylightCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._frame_id}_calendar"

    @property
    def event(self) -> CalendarEvent | None:
        """The current or next upcoming event (from the cached window)."""
        now = dt_util.now()
        events = sorted(
            (e for e in self._iter_events() if e is not None),
            key=lambda e: _sort_key(e.start),
        )
        # currently running
        for ev in events:
            if _contains(ev, now):
                return ev
        # otherwise next upcoming
        for ev in events:
            if _sort_key(ev.start) >= now.timestamp():
                return ev
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Range query — hits the API directly for accuracy."""
        tz = dt_util.get_default_time_zone()
        raw = await self.coordinator.client.async_get_calendar_events(
            start_date, end_date, timezone_name=str(tz)
        )
        out: list[CalendarEvent] = []
        for item in raw:
            ev = _to_event(item)
            if ev is not None:
                out.append(ev)
        return out

    def _iter_events(self):
        for item in self.coordinator.data.get("events", []):
            yield _to_event(item)

    # -- writes ---------------------------------------------------------------
    async def async_create_event(self, **kwargs: Any) -> None:
        """Create an event from Home Assistant."""
        attributes = _event_kwargs_to_attributes(kwargs)
        await self.coordinator.client.async_create_calendar_event(attributes)
        await self.coordinator.async_request_refresh()

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Delete an event by its Skylight id."""
        await self.coordinator.client.async_delete_calendar_event(uid)
        await self.coordinator.async_request_refresh()

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Update an existing event."""
        attributes = _event_kwargs_to_attributes(event)
        await self.coordinator.client.async_update_calendar_event(uid, attributes)
        await self.coordinator.async_request_refresh()


def _attrs(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("attributes", {}) if isinstance(item, dict) else {}


def _event_kwargs_to_attributes(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Map Home Assistant calendar create/update kwargs to a flat Skylight body."""
    dtstart = kwargs.get("dtstart")
    dtend = kwargs.get("dtend")
    all_day = dtstart is not None and not isinstance(dtstart, datetime)

    attributes: dict[str, Any] = {
        "summary": kwargs.get("summary"),
        "all_day": all_day,
        "description": kwargs.get("description"),
        "location": kwargs.get("location"),
        "rrule": kwargs.get("rrule"),
    }
    if dtstart is not None:
        attributes["starts_at"] = dtstart.isoformat()
    if dtend is not None:
        attributes["ends_at"] = dtend.isoformat()
    if all_day:
        attributes["timezone"] = None
    else:
        tz = None
        if isinstance(dtstart, datetime) and dtstart.tzinfo is not None:
            tz = getattr(dtstart.tzinfo, "key", None)
        attributes["timezone"] = tz or str(dt_util.get_default_time_zone())

    # drop keys HA didn't provide so we don't overwrite with null on update
    return {k: v for k, v in attributes.items() if v is not None or k == "timezone"}


def _to_event(item: dict[str, Any]) -> CalendarEvent | None:
    a = _attrs(item)
    start_raw = a.get("starts_at") or a.get("start")
    end_raw = a.get("ends_at") or a.get("end")
    if not start_raw:
        return None

    all_day = bool(a.get("all_day"))
    start = _parse(start_raw, all_day)
    end = _parse(end_raw, all_day) if end_raw else None
    if start is None:
        return None
    if end is None:
        end = (
            (start + timedelta(days=1))
            if isinstance(start, date) and not isinstance(start, datetime)
            else start + timedelta(hours=1)
        )

    return CalendarEvent(
        start=start,
        end=end,
        summary=a.get("summary") or "(no title)",
        description=a.get("description"),
        location=a.get("location"),
        # Use the Skylight resource id as the UID so HA delete/update target
        # the right record via /calendar_events/{id}.
        uid=str(item.get("id")),
        recurrence_id=a.get("master_event_id"),
        rrule=a.get("rrule"),
    )


def _parse(value: str, all_day: bool) -> datetime | date | None:
    if not value:
        return None
    if all_day:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    parsed = dt_util.parse_datetime(value)
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
        return parsed
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _sort_key(value: datetime | date) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    return dt_util.start_of_local_day(value).timestamp()


def _contains(ev: CalendarEvent, now: datetime) -> bool:
    start = ev.start
    end = ev.end
    if not isinstance(start, datetime):
        start = dt_util.start_of_local_day(start)
    if not isinstance(end, datetime):
        end = dt_util.start_of_local_day(end)
    return start <= now < end
