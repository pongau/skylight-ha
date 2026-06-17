"""Data update coordinator for Skylight."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SkylightApiClient, SkylightAuthError, SkylightError
from .const import (
    CALENDAR_LOOKAHEAD_DAYS,
    CALENDAR_LOOKBACK_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SkylightCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls Skylight for the whole household: profiles, events, chores, lists,
    meals and rewards. Calendar range queries go straight to the API; this
    coordinator keeps a cached window for entity state and attributes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SkylightApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        tz = dt_util.get_default_time_zone()
        now = dt_util.now()
        start = now - timedelta(days=CALENDAR_LOOKBACK_DAYS)
        end = now + timedelta(days=CALENDAR_LOOKAHEAD_DAYS)

        try:
            categories = await self.client.async_get_categories()
            events = await self.client.async_get_calendar_events(
                start, end, timezone_name=str(tz)
            )
            chores = await self._safe(self.client.async_get_chores(
                after=start.date(), before=end.date()
            ))
            lists = await self._safe(self.client.async_get_lists())
            reward_points = await self._safe(self.client.async_get_reward_points())
            rewards = await self._safe(self.client.async_get_rewards())
            recipes = await self._safe(self.client.async_get_recipes())
            sittings = await self._safe(self.client.async_get_meal_sittings())

            # fetch items for each list
            list_items: dict[str, list[dict[str, Any]]] = {}
            for lst in lists or []:
                lid = str(lst.get("id"))
                list_items[lid] = await self._safe(
                    self.client.async_get_list_items(lid)
                ) or []
        except SkylightAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except SkylightError as err:
            raise UpdateFailed(f"Error talking to Skylight: {err}") from err

        profiles = [
            c for c in categories if _attr(c).get("linked_to_profile")
        ]
        labels = [
            c for c in categories if not _attr(c).get("linked_to_profile")
        ]

        return {
            "categories": categories,
            "profiles": profiles,
            "labels": labels,
            "events": events,
            "chores": chores or [],
            "lists": lists or [],
            "list_items": list_items,
            "rewards": rewards or [],
            "reward_points": reward_points or [],
            "recipes": recipes or [],
            "sittings": sittings or [],
        }

    async def _safe(self, coro) -> Any:
        """Run an optional fetch; tolerate endpoints that 404/err on a frame."""
        try:
            return await coro
        except SkylightAuthError:
            raise
        except SkylightError as err:
            _LOGGER.debug("Optional Skylight fetch failed: %s", err)
            return None


def _attr(resource: dict[str, Any]) -> dict[str, Any]:
    return resource.get("attributes", {}) if isinstance(resource, dict) else {}
