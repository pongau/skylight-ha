"""Sensor platform for Skylight."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SkylightConfigEntry
from .chore_summary import build_member_summary
from .const import EXCLUDED_PROFILE_LABELS
from .coordinator import SkylightCoordinator
from .entity import SkylightEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkylightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SkylightEntity] = [
        SkylightEventsTodaySensor(coordinator),
        SkylightChoresDueTodaySensor(coordinator),
    ]

    known_lists: set[str] = set()
    known_profiles: set[str] = set()
    known_members: set[str] = set()

    @callback
    def _discover() -> None:
        new: list[SkylightEntity] = []
        for lst in coordinator.data.get("lists", []):
            lid = str(lst.get("id"))
            if lid not in known_lists:
                known_lists.add(lid)
                new.append(SkylightListSensor(coordinator, lid))
        if coordinator.data.get("reward_points"):
            for prof in coordinator.data.get("profiles", []):
                pid = str(prof.get("id"))
                if pid not in known_profiles:
                    known_profiles.add(pid)
                    new.append(SkylightProfilePointsSensor(coordinator, pid))
        for prof in coordinator.data.get("profiles", []):
            if _attrs(prof).get("label") in EXCLUDED_PROFILE_LABELS:
                continue
            pid = str(prof.get("id"))
            if pid not in known_members:
                known_members.add(pid)
                new.append(SkylightMemberChoresSensor(coordinator, pid))
        if new:
            async_add_entities(new)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))
    async_add_entities(entities)


def _attrs(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("attributes", {}) if isinstance(item, dict) else {}


def _category_id(item: dict[str, Any]) -> str | None:
    rel = item.get("relationships", {}) if isinstance(item, dict) else {}
    cat = (rel.get("category") or {}).get("data") if isinstance(rel, dict) else None
    if isinstance(cat, dict):
        return str(cat.get("id"))
    a = _attrs(item)
    if a.get("category_id") is not None:
        return str(a["category_id"])
    return None


def _is_today(value: str | None) -> bool:
    if not value:
        return False
    parsed = dt_util.parse_datetime(value)
    if parsed is not None:
        return dt_util.as_local(parsed).date() == dt_util.now().date()
    try:
        return date.fromisoformat(value[:10]) == dt_util.now().date()
    except ValueError:
        return False


class SkylightEventsTodaySensor(SkylightEntity, SensorEntity):
    """Number of calendar events occurring today."""

    _attr_name = "Events today"
    _attr_icon = "mdi:calendar-today"
    _attr_native_unit_of_measurement = "events"

    def __init__(self, coordinator: SkylightCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._frame_id}_events_today"

    @property
    def _today_events(self) -> list[dict[str, Any]]:
        out = []
        for e in self.coordinator.data.get("events", []):
            a = _attrs(e)
            if _is_today(a.get("starts_at") or a.get("start")):
                out.append(e)
        return out

    @property
    def native_value(self) -> int:
        return len(self._today_events)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "events": [
                _attrs(e).get("summary") for e in self._today_events
            ]
        }


class SkylightChoresDueTodaySensor(SkylightEntity, SensorEntity):
    """Number of chores due today that are not completed."""

    _attr_name = "Chores due today"
    _attr_icon = "mdi:broom"
    _attr_native_unit_of_measurement = "chores"

    def __init__(self, coordinator: SkylightCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._frame_id}_chores_due_today"

    @property
    def _due(self) -> list[dict[str, Any]]:
        out = []
        for c in self.coordinator.data.get("chores", []):
            a = _attrs(c)
            if a.get("completed_on"):
                continue
            if _is_today(a.get("start")):
                out.append(c)
        return out

    @property
    def native_value(self) -> int:
        return len(self._due)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"chores": [_attrs(c).get("summary") for c in self._due]}


class SkylightListSensor(SkylightEntity, SensorEntity):
    """Number of pending items in a Skylight list."""

    _attr_icon = "mdi:format-list-checks"
    _attr_native_unit_of_measurement = "items"

    def __init__(self, coordinator: SkylightCoordinator, list_id: str) -> None:
        super().__init__(coordinator)
        self._list_id = list_id
        self._attr_unique_id = f"{self._frame_id}_list_{list_id}"

    def _list(self) -> dict[str, Any]:
        for lst in self.coordinator.data.get("lists", []):
            if str(lst.get("id")) == self._list_id:
                return lst
        return {}

    @property
    def name(self) -> str:
        label = _attrs(self._list()).get("label") or f"List {self._list_id}"
        return f"{label} list"

    def _items(self) -> list[dict[str, Any]]:
        return self.coordinator.data.get("list_items", {}).get(self._list_id, [])

    @property
    def native_value(self) -> int:
        return sum(
            1 for i in self._items() if _attrs(i).get("status") != "completed"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "kind": _attrs(self._list()).get("kind"),
            "pending": [
                _attrs(i).get("label")
                for i in self._items()
                if _attrs(i).get("status") != "completed"
            ],
        }


class SkylightProfilePointsSensor(SkylightEntity, SensorEntity):
    """Reward points for a profile."""

    _attr_icon = "mdi:star-circle"
    _attr_native_unit_of_measurement = "points"

    def __init__(self, coordinator: SkylightCoordinator, profile_id: str) -> None:
        super().__init__(coordinator)
        self._profile_id = profile_id
        self._attr_unique_id = f"{self._frame_id}_points_{profile_id}"

    def _profile(self) -> dict[str, Any]:
        for p in self.coordinator.data.get("profiles", []):
            if str(p.get("id")) == self._profile_id:
                return p
        return {}

    @property
    def name(self) -> str:
        label = _attrs(self._profile()).get("label") or f"Profile {self._profile_id}"
        return f"{label} points"

    @property
    def native_value(self) -> int | None:
        for rp in self.coordinator.data.get("reward_points", []):
            if _category_id(rp) == self._profile_id:
                a = _attrs(rp)
                for key in ("points", "balance", "total", "value"):
                    if a.get(key) is not None:
                        return a[key]
        return None


class SkylightMemberChoresSensor(SkylightEntity, SensorEntity):
    """One family member's chores for today.

    State is the number of incomplete chores remaining today; the full
    breakdown is in attributes. See chore_summary.build_member_summary.
    """

    _attr_icon = "mdi:broom"
    _attr_native_unit_of_measurement = "chores"

    def __init__(self, coordinator: SkylightCoordinator, profile_id: str) -> None:
        super().__init__(coordinator)
        self._profile_id = profile_id
        self._attr_unique_id = f"{self._frame_id}_chores_{profile_id}"

    def _profile(self) -> dict[str, Any]:
        for prof in self.coordinator.data.get("profiles", []):
            if str(prof.get("id")) == self._profile_id:
                return prof
        return {}

    @property
    def name(self) -> str:
        label = _attrs(self._profile()).get("label") or f"Profile {self._profile_id}"
        return f"{label} chores"

    def _summary(self) -> dict[str, Any]:
        return build_member_summary(
            self.coordinator.data.get("chores", []),
            self._profile_id,
            _attrs(self._profile()).get("label"),
            dt_util.now().date(),
        )

    @property
    def native_value(self) -> int:
        return self._summary()["state"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._summary()["attributes"]
