"""Async client for the (unofficial) Skylight family-calendar REST API.

Auth model (reverse-engineered):
  * POST /api/sessions  with JSON {email, password, unique_id}
    -> {access_token, refresh_token, user_id, ...}  (opaque 43-char tokens)
  * Every request sends:
        Authorization: Bearer <access_token>
        Skylight-Api-Version: 2026-05-01
        User-Agent: SkylightMobile (web)
        Accept: application/json
  * Access tokens expire after ~2h. We simply re-authenticate with the stored
    credentials when a token is missing/expired or a 401 is returned. (A
    refresh_token grant exists too, but re-login is simplest and robust.)

The same credentials/token grant FULL account read+write access; there is no
scoped API key. Treat them as secrets.

Responses are JSON:API shaped: {"data": [{"type","id","attributes",
"relationships"}], "included": [...]}.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import aiohttp

from .const import (
    API_VERSION,
    API_VERSION_HEADER,
    BASE_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class SkylightError(Exception):
    """Base error."""


class SkylightAuthError(SkylightError):
    """Raised when authentication fails (bad credentials / token)."""


class SkylightApiClient:
    """Thin async wrapper over the Skylight private API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        device_id: str,
        email: str | None = None,
        password: str | None = None,
        access_token: str | None = None,
        frame_id: str | None = None,
    ) -> None:
        self._session = session
        self._device_id = device_id
        self._email = email
        self._password = password
        self._token = access_token
        # When a token is supplied directly (no credentials) we cannot re-login.
        self._static_token = access_token is not None and not (email and password)
        # The current web app uses `Authorization: Bearer <token>`; some older
        # captures use `Authorization: Basic <token>`. We default to Bearer and
        # auto-detect on validate().
        self._auth_scheme = "Bearer"
        self.frame_id = frame_id

    # -- auth -----------------------------------------------------------------
    @property
    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            API_VERSION_HEADER: API_VERSION,
            "User-Agent": USER_AGENT,
        }

    async def async_login(self) -> str:
        """Authenticate with email/password and store the access token."""
        if not (self._email and self._password):
            raise SkylightAuthError("No credentials configured to log in with")

        body = {
            "email": self._email,
            "password": self._password,
            "unique_id": self._device_id,
        }
        async with self._session.post(
            f"{BASE_URL}/sessions", headers=self._base_headers, json=body
        ) as resp:
            payload = await _safe_json(resp)
            if resp.status in (401, 403) or "errors" in (payload or {}):
                raise SkylightAuthError(_errors_text(payload) or f"HTTP {resp.status}")
            resp.raise_for_status()

        token = _extract_token(payload)
        if not token:
            raise SkylightAuthError("Login response did not contain an access token")
        self._token = token
        return token

    async def async_validate(self) -> None:
        """Ensure we have a usable token and the correct auth scheme."""
        if self._token is None:
            await self.async_login()

        # Probe the token; if Bearer is rejected, fall back to Basic.
        for scheme in ("Bearer", "Basic"):
            self._auth_scheme = scheme
            try:
                await self.async_get_frames()
                return
            except SkylightAuthError:
                continue
        raise SkylightAuthError("Token was not accepted as Bearer or Basic")

    # -- core request ---------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        _retry: bool = True,
    ) -> Any:
        if self._token is None and not self._static_token:
            await self.async_login()

        headers = dict(self._base_headers)
        if self._token:
            headers["Authorization"] = f"{self._auth_scheme} {self._token}"

        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        async with self._session.request(
            method, url, headers=headers, params=_clean_params(params), json=json
        ) as resp:
            if resp.status == 401 and _retry and not self._static_token:
                # token expired -> re-login and retry once
                _LOGGER.debug("401 from Skylight; re-authenticating")
                await self.async_login()
                return await self._request(
                    method, path, params=params, json=json, _retry=False
                )
            if resp.status == 401:
                raise SkylightAuthError("Unauthorized (token expired or invalid)")
            if resp.status == 204:
                return None
            payload = await _safe_json(resp)
            if resp.status >= 400:
                raise SkylightError(
                    _errors_text(payload) or f"HTTP {resp.status} for {method} {path}"
                )
            return payload

    def _frame(self, frame_id: str | None) -> str:
        fid = frame_id or self.frame_id
        if not fid:
            raise SkylightError("No frame_id configured")
        return fid

    # -- reads ----------------------------------------------------------------
    async def async_get_frames(self) -> list[dict[str, Any]]:
        """List frames (calendars/accounts) available to this login."""
        data = await self._request("GET", "/frames")
        return _data_list(data)

    async def async_get_frame(self, frame_id: str | None = None) -> dict[str, Any]:
        data = await self._request("GET", f"/frames/{self._frame(frame_id)}")
        return _data_obj(data)

    async def async_get_categories(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Profiles + labels (JSON:API 'category' resources)."""
        data = await self._request(
            "GET", f"/frames/{self._frame(frame_id)}/categories"
        )
        return _data_list(data)

    async def async_get_calendar_events(
        self,
        start: datetime | date,
        end: datetime | date,
        *,
        frame_id: str | None = None,
        timezone_name: str = "UTC",
    ) -> list[dict[str, Any]]:
        params = {
            "date_min": _as_date_str(start),
            "date_max": _as_date_str(end),
            "timezone": timezone_name,
        }
        data = await self._request(
            "GET",
            f"/frames/{self._frame(frame_id)}/calendar_events",
            params=params,
        )
        return _data_list(data)

    async def async_get_chores(
        self,
        after: date | datetime | None = None,
        before: date | datetime | None = None,
        *,
        frame_id: str | None = None,
        include_late: bool = True,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"include_late": str(include_late).lower()}
        if after is not None:
            params["after"] = _as_date_str(after)
        if before is not None:
            params["before"] = _as_date_str(before)
        data = await self._request(
            "GET", f"/frames/{self._frame(frame_id)}/chores", params=params
        )
        return _data_list(data)

    async def async_get_lists(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/frames/{self._frame(frame_id)}/lists")
        return _data_list(data)

    async def async_get_list(
        self, list_id: str, *, frame_id: str | None = None
    ) -> dict[str, Any]:
        """A single list including its items (in `included`)."""
        data = await self._request(
            "GET", f"/frames/{self._frame(frame_id)}/lists/{list_id}"
        )
        obj = _data_obj(data)
        obj["_included"] = data.get("included", []) if isinstance(data, dict) else []
        return obj

    async def async_get_list_items(
        self, list_id: str, *, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/frames/{self._frame(frame_id)}/lists/{list_id}/list_items",
        )
        return _data_list(data)

    async def async_get_rewards(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/frames/{self._frame(frame_id)}/rewards")
        return _data_list(data)

    async def async_get_reward_points(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/frames/{self._frame(frame_id)}/reward_points"
        )
        return _data_list(data)

    async def async_get_recipes(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/frames/{self._frame(frame_id)}/meals/recipes"
        )
        return _data_list(data)

    async def async_get_meal_sittings(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/frames/{self._frame(frame_id)}/meals/sittings"
        )
        return _data_list(data)

    async def async_get_task_box_items(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/frames/{self._frame(frame_id)}/task_box/items"
        )
        return _data_list(data)

    async def async_get_source_calendars(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/frames/{self._frame(frame_id)}/source_calendars"
        )
        return _data_list(data)

    async def async_get_devices(
        self, frame_id: str | None = None
    ) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/frames/{self._frame(frame_id)}/devices")
        return _data_list(data)

    # -- writes (not used by the read-only entities; here for optionality) -----
    async def async_create_calendar_event(
        self, attributes: dict[str, Any], *, frame_id: str | None = None
    ) -> dict[str, Any]:
        body = {"data": {"type": "calendar_event", "attributes": attributes}}
        data = await self._request(
            "POST", f"/frames/{self._frame(frame_id)}/calendar_events", json=body
        )
        return _data_obj(data)

    async def async_update_calendar_event(
        self, event_id: str, attributes: dict[str, Any], *, frame_id: str | None = None
    ) -> dict[str, Any]:
        body = {"data": {"type": "calendar_event", "attributes": attributes}}
        data = await self._request(
            "PATCH",
            f"/frames/{self._frame(frame_id)}/calendar_events/{event_id}",
            json=body,
        )
        return _data_obj(data)

    async def async_delete_calendar_event(
        self, event_id: str, *, frame_id: str | None = None
    ) -> None:
        await self._request(
            "DELETE",
            f"/frames/{self._frame(frame_id)}/calendar_events/{event_id}",
        )

    async def async_complete_chore(
        self,
        chore_id: str,
        *,
        completed_on: date | None = None,
        frame_id: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {}
        if completed_on is not None:
            body["completed_on"] = _as_date_str(completed_on)
        return await self._request(
            "POST",
            f"/frames/{self._frame(frame_id)}/chores/{chore_id}/completions",
            json=body or None,
        )

    async def async_create_list_item(
        self, list_id: str, label: str, *, frame_id: str | None = None
    ) -> dict[str, Any]:
        body = {"data": {"type": "list_item", "attributes": {"label": label}}}
        data = await self._request(
            "POST",
            f"/frames/{self._frame(frame_id)}/lists/{list_id}/list_items",
            json=body,
        )
        return _data_obj(data)

    async def async_update_list_item(
        self,
        list_id: str,
        item_id: str,
        attributes: dict[str, Any],
        *,
        frame_id: str | None = None,
    ) -> dict[str, Any]:
        body = {"data": {"type": "list_item", "attributes": attributes}}
        data = await self._request(
            "PATCH",
            f"/frames/{self._frame(frame_id)}/lists/{list_id}/list_items/{item_id}",
            json=body,
        )
        return _data_obj(data)

    async def async_delete_list_item(
        self, list_id: str, item_id: str, *, frame_id: str | None = None
    ) -> None:
        await self._request(
            "DELETE",
            f"/frames/{self._frame(frame_id)}/lists/{list_id}/list_items/{item_id}",
        )

    async def async_delete_category(
        self,
        category_id: str,
        *,
        reassign_to_category_id: str | None = None,
        frame_id: str | None = None,
    ) -> None:
        """Delete a profile/label. With reassign, this is Skylight's 'merge'."""
        params = (
            {"reassign_to_category_id": reassign_to_category_id}
            if reassign_to_category_id
            else None
        )
        await self._request(
            "DELETE",
            f"/frames/{self._frame(frame_id)}/categories/{category_id}",
            params=params,
        )


# --- helpers -----------------------------------------------------------------
def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    return {k: v for k, v in params.items() if v is not None}


def _as_date_str(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat()
    return value.isoformat()


async def _safe_json(resp: aiohttp.ClientResponse) -> Any:
    try:
        return await resp.json(content_type=None)
    except Exception:  # noqa: BLE001
        return None


def _errors_text(payload: Any) -> str | None:
    if isinstance(payload, dict) and payload.get("errors"):
        errs = payload["errors"]
        if isinstance(errs, list):
            return "; ".join(str(e) for e in errs)
        return str(errs)
    return None


def _extract_token(payload: Any) -> str | None:
    """Find the access token in a login response, tolerating shape variations."""
    if not isinstance(payload, dict):
        return None
    token_keys = ("access_token", "accessToken", "token", "authToken")
    for key in token_keys:
        if isinstance(payload.get(key), str):
            return payload[key]
    # JSON:API / nested wrappers: {"data": {...}} or {"user": {...}}
    for wrapper in ("data", "user"):
        node = payload.get(wrapper)
        if isinstance(node, dict):
            attrs = node.get("attributes", node)
            if isinstance(attrs, dict):
                for key in token_keys:
                    if isinstance(attrs.get(key), str):
                        return attrs[key]
    return None


def _data_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    if isinstance(payload, list):
        return payload
    return []


def _data_obj(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    return {}
