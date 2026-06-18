"""Constants for the Skylight (family calendar) integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "skylight"

# --- API ---------------------------------------------------------------------
# This is the PRIVATE REST API used by the Skylight family-calendar apps
# (ourskylight.com). It is unofficial and reverse-engineered; Skylight can
# change it at any time.
HOST = "https://app.ourskylight.com"
BASE_URL = f"{HOST}/api"

# OAuth2 (Doorkeeper) token endpoint — refresh-token grant, public client.
# The old email/password POST /api/sessions flow is sunset.
OAUTH_TOKEN_URL = f"{HOST}/oauth/token"
OAUTH_CLIENT_ID = "skylight-mobile"

# Data endpoints still want a recognised API version header.
API_VERSION_HEADER = "Skylight-Api-Version"
API_VERSION = "2026-05-01"
USER_AGENT = "SkylightMobile (web)"

# Access tokens live ~2h; refresh tokens rotate on every use.
ACCESS_TOKEN_TTL = timedelta(hours=2)

# --- Config entry keys -------------------------------------------------------
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN = "access_token"
CONF_TOKEN_EXPIRY = "token_expiry"
CONF_FRAME_ID = "frame_id"
CONF_FRAME_NAME = "frame_name"
CONF_AUTH_METHOD = "auth_method"

AUTH_METHOD_REFRESH = "refresh_token"
AUTH_METHOD_TOKEN = "token"

# --- Polling -----------------------------------------------------------------
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
# How far forward/back the calendar coordinator keeps events cached for state.
CALENDAR_LOOKAHEAD_DAYS = 30
CALENDAR_LOOKBACK_DAYS = 1

PLATFORMS = ["calendar", "sensor", "todo"]
