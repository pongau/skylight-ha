"""Constants for the Skylight (family calendar) integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "skylight"

# --- API ---------------------------------------------------------------------
# This is the PRIVATE REST API used by the Skylight family-calendar apps
# (ourskylight.com). It is unofficial and reverse-engineered; Skylight can
# change it at any time.
BASE_URL = "https://app.ourskylight.com/api"

# The API rejects clients that do not advertise a recent app version with
# `{"errors":["This version of Skylight is no longer supported..."]}`.
API_VERSION_HEADER = "Skylight-Api-Version"
API_VERSION = "2026-05-01"
USER_AGENT = "SkylightMobile (web)"

# Access tokens are opaque (not JWTs) and live ~2h (accessTokenLifeSpan).
ACCESS_TOKEN_TTL = timedelta(hours=2)
# Refresh a little early to avoid mid-poll expiry.
TOKEN_REFRESH_SKEW = timedelta(minutes=5)

# --- Config entry keys -------------------------------------------------------
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_TOKEN = "access_token"
CONF_FRAME_ID = "frame_id"
CONF_FRAME_NAME = "frame_name"
CONF_DEVICE_ID = "device_id"
CONF_AUTH_METHOD = "auth_method"

AUTH_METHOD_PASSWORD = "password"
AUTH_METHOD_TOKEN = "token"

# --- Polling -----------------------------------------------------------------
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
# How far forward/back the calendar coordinator keeps events cached for state.
CALENDAR_LOOKAHEAD_DAYS = 30
CALENDAR_LOOKBACK_DAYS = 1

PLATFORMS = ["calendar", "sensor", "todo"]
