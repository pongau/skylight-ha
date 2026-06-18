"""Config flow for Skylight."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkylightApiClient, SkylightAuthError, SkylightError
from .const import (
    AUTH_METHOD_REFRESH,
    AUTH_METHOD_TOKEN,
    CONF_AUTH_METHOD,
    CONF_FRAME_ID,
    CONF_FRAME_NAME,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN,
    DOMAIN,
)


def _frame_label(frame: dict[str, Any]) -> str:
    attrs = frame.get("attributes", {}) if isinstance(frame, dict) else {}
    name = attrs.get("name") or attrs.get("label") or f"Frame {frame.get('id')}"
    return f"{name} ({frame.get('id')})"


class SkylightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Skylight."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: SkylightApiClient | None = None
        self._base: dict[str, Any] = {}
        self._frames: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose authentication method."""
        if user_input is not None:
            if user_input[CONF_AUTH_METHOD] == AUTH_METHOD_TOKEN:
                return await self.async_step_token()
            return await self.async_step_refresh()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTH_METHOD, default=AUTH_METHOD_REFRESH
                    ): vol.In(
                        {
                            AUTH_METHOD_REFRESH: "Refresh token (recommended, durable)",
                            AUTH_METHOD_TOKEN: "Access token (temporary, ~2h)",
                        }
                    )
                }
            ),
        )

    async def async_step_refresh(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = SkylightApiClient(
                session, refresh_token=user_input[CONF_REFRESH_TOKEN]
            )
            try:
                await client.async_validate()
                self._frames = await client.async_get_frames()
            except SkylightAuthError:
                errors["base"] = "invalid_auth"
            except SkylightError:
                errors["base"] = "cannot_connect"
            else:
                self._client = client
                # store the ROTATED refresh token, not the one the user pasted
                self._base = {CONF_REFRESH_TOKEN: client.refresh_token}
                return await self.async_step_frame()

        return self.async_show_form(
            step_id="refresh",
            data_schema=vol.Schema({vol.Required(CONF_REFRESH_TOKEN): str}),
            errors=errors,
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = SkylightApiClient(
                session, access_token=user_input[CONF_TOKEN]
            )
            try:
                self._frames = await client.async_get_frames()
            except SkylightAuthError:
                errors["base"] = "invalid_auth"
            except SkylightError:
                errors["base"] = "cannot_connect"
            else:
                self._client = client
                self._base = {CONF_TOKEN: user_input[CONF_TOKEN]}
                return await self.async_step_frame()

        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )

    async def async_step_frame(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which frame (calendar) to expose."""
        if not self._frames:
            return self.async_abort(reason="no_frames")

        if user_input is None and len(self._frames) == 1:
            user_input = {CONF_FRAME_ID: str(self._frames[0].get("id"))}

        if user_input is not None:
            frame_id = user_input[CONF_FRAME_ID]
            frame = next(
                (f for f in self._frames if str(f.get("id")) == str(frame_id)),
                self._frames[0],
            )
            await self.async_set_unique_id(str(frame_id))
            self._abort_if_unique_id_configured()
            name = _frame_label(frame)
            return self.async_create_entry(
                title=name,
                data={
                    **self._base,
                    CONF_FRAME_ID: str(frame_id),
                    CONF_FRAME_NAME: name,
                },
            )

        return self.async_show_form(
            step_id="frame",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FRAME_ID): vol.In(
                        {str(f.get("id")): _frame_label(f) for f in self._frames}
                    )
                }
            ),
        )
