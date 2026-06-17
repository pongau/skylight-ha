"""Shared entity base for Skylight."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_FRAME_ID, CONF_FRAME_NAME, DOMAIN
from .coordinator import SkylightCoordinator


class SkylightEntity(CoordinatorEntity[SkylightCoordinator]):
    """Base entity tying everything to one Skylight frame device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SkylightCoordinator) -> None:
        super().__init__(coordinator)
        frame_id = coordinator.entry.data[CONF_FRAME_ID]
        frame_name = coordinator.entry.data.get(CONF_FRAME_NAME, f"Frame {frame_id}")
        self._frame_id = frame_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, frame_id)},
            manufacturer="Skylight",
            name=frame_name,
            model="Skylight Calendar",
            configuration_url="https://ourskylight.com",
        )
