"""The Skylight (family calendar) integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkylightApiClient, SkylightAuthError, SkylightError
from .const import (
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_FRAME_ID,
    CONF_PASSWORD,
    CONF_TOKEN,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SkylightCoordinator

_LOGGER = logging.getLogger(__name__)

type SkylightConfigEntry = ConfigEntry[SkylightCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SkylightConfigEntry) -> bool:
    """Set up Skylight from a config entry."""
    session = async_get_clientsession(hass)
    client = SkylightApiClient(
        session,
        device_id=entry.data[CONF_DEVICE_ID],
        email=entry.data.get(CONF_EMAIL),
        password=entry.data.get(CONF_PASSWORD),
        access_token=entry.data.get(CONF_TOKEN),
        frame_id=entry.data[CONF_FRAME_ID],
    )

    try:
        await client.async_validate()
    except SkylightAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SkylightError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = SkylightCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SkylightConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
