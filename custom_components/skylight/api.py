"""Async client for the (unofficial) Skylight family-calendar REST API.

Auth model (reverse-engineered, June 2026):
  The old email/password ``POST /api/sessions`` flow is **sunset** — every
  ``Skylight-Api-Version`` is rejected as "no longer supported". The apps now
  use a standard OAuth2 setup:

    POST https://app.ourskylight.com/oauth/token
      { grant_type: "refresh_token", refresh_token: <rt>,
        client_id: "skylight-mobile" }
    -> { access_token, refresh_token (ROTATED), token_type: "Bearer",
         expires_in: 7200, scope: "everything" }

  So this client is seeded with a **refresh token** (captured once from the
  app) and exchanges it for short-lived (2h) Bearer access tokens. Refresh
  tokens rotate on every use, so the new one must be persisted — the caller
  passes ``on_token_update`` to save it back to the config entry.

  API data calls use:
    Authorization: Bearer <access_token>
    Skylight-Api-Version: 2026-05-01   (accepted for data endpoints)
    User-Agent: SkylightMobile (web)
    Accept: application/json

  The token grants full account read+write (scope "everything"). Treat the
  refresh token as a secret.

Responses are JSON:API shaped: {"data": [...], "included": [...]}.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any

import aiohttp

from .const import (
    API_VERSION,
    API_VERSION_HEADER,
    BASE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_TOKEN_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

# Refresh this many seconds before the access token actually expires.
_EXPIRY_SKEW = 300


class SkylightError(Exception):
    """Base error."""


class SkylightAuthError(SkylightError):
    """Raised when authentication fails (bad/expired refresh token)."""


class SkylightApiClient:
    """Thin async wrapper over the Skylight private API (OAuth refresh-token)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        refresh_token: str | None = None,
        access_token: str | None = None,
        token_expiry: float | None = None,
        frame_id: str | None = None,
        on_token_update: Callable[[str, str, float], None] | None = None,
    ) -> None:
        self._session = session
        self._refresh_token = refresh_token
        self._token = access_token
        self._expiry = token_expiry or 0.0
        # If we only have a static access token (no refresh token) we cannot
        # renew it — it just dies after ~2h.
        self._can_refresh = refresh_token is not None
        self._on_token_update = on_token_update
        self.frame_id = frame_id

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    # -- auth -----------------------------------------------------------------
    @property
    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            API_VERSION_HEADER: API_VERSION,
            "User-Agent": USER_AGENT,
        }

    async def async_refresh(self) -> None:
        """Exchange the refresh token for a fresh access token (rotating)."""
        if not self._refresh_token:
            raise SkylightAuthError("No refresh token configured")

        body = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": OAUTH_CLIENT_ID,
        }
        async with self._session.post(
            OAUTH_TOKEN_URL,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=body,
        ) as resp:
            payload = await _safe_json(resp)
            if resp.status in (400, 401):
                raise SkylightAuthError(
                    _oauth_error(payload) or "Refresh token rejected"
                )
            if resp.status >= 400 or not isinstance(payload, dict):
                raise SkylightError(f"Token endpoint returned HTTP {resp.status}")

        token = payload.get("access_token")
        if not token:
            raise SkylightAuthError("Token response did not contain an access token")
        self._token = token
        expires_in = payload.get("expires_in") or 7200
        self._expiry = time.time() + float(expires_in)
        # Persist the rotated refresh token.
        new_rt = payload.get("refresh_token")
        if new_rt:
            self._refresh_token = new_rt
        if self._on_token_update and self._refresh_token:
            self._on_token_update(self._refresh_token, self._token, self._expiry)

    async def async_validate(self) -> None:
        """Ensure we have a working token; refresh if we can."""
        if self._can_refresh:
            await self.async_refresh()
        # Confirm the token actually works.
        await self.async_get_frames()

    async def _ensure_token(self) -> None:
        if self._token and time.time() < self._expiry - _EXPIRY_SKEW:
            return
        if self._can_refresh:
            await self.async_refresh()
        elif not self._token:
            raise SkylightAuthError("No access token available")

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
        await self._ensure_token()

        headers = dict(self._base_headers)
        headers["Authorization"] = f"Bearer {self._token}"

        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        async with self._session.request(
            method, url, headers=headers, params=_clean_params(params), json=json
        ) as resp:
            if resp.status == 401 and _retry and self._can_refresh:
                _LOGGER.debug("401 from Skylight; refreshing access token")
                await self.async_refresh()
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

    # -- writes ---------------------------------------------------------------
    async def async_create_calendar_event(
        self, attributes: dict[str, Any], *, frame_id: str | None = None
    ) -> dict[str, Any]:
        # Flat body (verified from captured traffic): {summary, starts_at,
        # ends_at, all_day, timezone, description, location, rrule, category_ids}
        data = await self._request(
            "POST",
            f"/frames/{self._frame(frame_id)}/calendar_events",
            json=attributes,
        )
        return _data_obj(data)

    async def async_update_calendar_event(
        self, event_id: str, attributes: dict[str, Any], *, frame_id: str | None = None
    ) -> dict[str, Any]:
        data = await self._request(
            "PATCH",
            f"/frames/{self._frame(frame_id)}/calendar_events/{event_id}",
            json=attributes,
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
        # Flat body (verified): {"label": "..."}
        data = await self._request(
            "POST",
            f"/frames/{self._frame(frame_id)}/lists/{list_id}/list_items",
            json={"label": label},
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
        data = await self._request(
            "PATCH",
            f"/frames/{self._frame(frame_id)}/lists/{list_id}/list_items/{item_id}",
            json=attributes,
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


def _oauth_error(payload: Any) -> str | None:
    if isinstance(payload, dict):
        return payload.get("error_description") or payload.get("error")
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
