"""To-do platform for Skylight lists (read-only).

Each Skylight list (shopping / to_do) is surfaced as a Home Assistant to-do
list. Items are read-only here; the API client already has create/update/delete
helpers if you later want to make these writable (set the supported features
and implement the async_create/update/delete methods).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SkylightConfigEntry
from .coordinator import SkylightCoordinator
from .entity import SkylightEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkylightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _discover() -> None:
        new = []
        for lst in coordinator.data.get("lists", []):
            lid = str(lst.get("id"))
            if lid not in known:
                known.add(lid)
                new.append(SkylightTodoList(coordinator, lid))
        if new:
            async_add_entities(new)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


def _attrs(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("attributes", {}) if isinstance(item, dict) else {}


class SkylightTodoList(SkylightEntity, TodoListEntity):
    """A Skylight list surfaced as an HA to-do list (read/write)."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: SkylightCoordinator, list_id: str) -> None:
        super().__init__(coordinator)
        self._list_id = list_id
        self._attr_unique_id = f"{self._frame_id}_todo_{list_id}"

    def _list(self) -> dict[str, Any]:
        for lst in self.coordinator.data.get("lists", []):
            if str(lst.get("id")) == self._list_id:
                return lst
        return {}

    @property
    def name(self) -> str:
        return _attrs(self._list()).get("label") or f"List {self._list_id}"

    @property
    def todo_items(self) -> list[TodoItem]:
        items = self.coordinator.data.get("list_items", {}).get(self._list_id, [])
        result: list[TodoItem] = []
        for it in items:
            a = _attrs(it)
            status = (
                TodoItemStatus.COMPLETED
                if a.get("status") == "completed"
                else TodoItemStatus.NEEDS_ACTION
            )
            result.append(
                TodoItem(
                    summary=a.get("label") or "(item)",
                    uid=str(it.get("id")),
                    status=status,
                )
            )
        return result

    # -- writes ---------------------------------------------------------------
    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self.coordinator.client.async_create_list_item(
            self._list_id, item.summary or ""
        )
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        attributes: dict[str, Any] = {}
        if item.summary is not None:
            attributes["label"] = item.summary
        if item.status is not None:
            attributes["status"] = (
                "completed"
                if item.status == TodoItemStatus.COMPLETED
                else "pending"
            )
        await self.coordinator.client.async_update_list_item(
            self._list_id, item.uid, attributes
        )
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self.coordinator.client.async_delete_list_item(self._list_id, uid)
        await self.coordinator.async_request_refresh()
