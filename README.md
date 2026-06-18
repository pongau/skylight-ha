# Skylight Calendar — Home Assistant integration

A custom Home Assistant integration that bridges your **Skylight family
calendar** (`ourskylight.com`) into Home Assistant.

It exposes your household's data as HA entities and supports **two-way edits**
for calendars and lists (create/update/delete events and to-do items from HA).

> ⚠️ **Unofficial.** Skylight has no public API for the family-calendar
> product. This talks to the private app API, reverse-engineered and documented
> in [`docs/API.md`](docs/API.md). It may break if Skylight changes things. Use
> only with your own account.

## What you get

One **device per Skylight frame**, with:

- 📅 **Calendar** entity — all events, queryable by Lovelace calendar cards and
  automations (`calendar.skylight_calendar`). **Read/write**: create, edit and
  delete events from Home Assistant.
- 🔢 **Sensors**
  - `Events today` (+ list of titles)
  - `Chores due today` (+ list)
  - One **points** sensor per profile (if rewards are enabled)
  - One **list** sensor per Skylight list (pending item count + items)
- ✅ **To-do lists** — each Skylight list (shopping / to-do) as a **read/write**
  HA to-do list (add, complete and remove items).

Covers the full Skylight surface: profiles, calendar, chores, lists, meals,
rewards.

## Installation

### HACS (custom repository)
1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add this repo, category **Integration**.
3. Install **Skylight Calendar**, then restart Home Assistant.

### Manual
Copy `custom_components/skylight/` into your HA `config/custom_components/`
folder and restart.

## Setup

**Settings → Devices & Services → Add Integration → Skylight.**

> ℹ️ Skylight's old email/password API is **sunset**, so login is token-based
> now (OAuth2 refresh tokens). See [`docs/API.md`](docs/API.md#authentication).

Choose one of:

- **Refresh token** (recommended, durable) — the integration exchanges it for
  2-hour access tokens and **auto-renews indefinitely**, persisting the rotated
  token each time.
- **Access token** (temporary) — works for ~2 hours, no auto-renew. Handy for a
  quick test.

**To capture a token:** sign in at `ourskylight.com`, open DevTools → Application
→ Local Storage → `ourskylight.com` → key `mmkv.default\auth-storage`, and copy
`state.refreshToken` (or `state.accessToken`).

Then pick which **frame** (calendar) to add. Add the integration again for more
frames.

## Security

- Tokens live in HA's encrypted config-entry store — never in code or logs.
  Rotated refresh tokens are persisted back to the entry automatically.
- ⚠️ A Skylight refresh token grants **full account access** (`scope:
  everything`, no finer scoping). Treat it like a password. Details in
  [`docs/API.md`](docs/API.md#security-note).
- Note: the refresh chain rotates, so using a token in HA will eventually log
  out other sessions that shared it (just sign in again where needed).

## Writes

Enabled for calendars and lists:

- **Calendar** — `CalendarEntityFeature.CREATE_EVENT | UPDATE_EVENT |
  DELETE_EVENT`. The create/update body is sent **flat** (`summary`,
  `starts_at`, `ends_at`, `all_day`, `timezone`, `description`, `location`,
  `rrule`), matching captured app traffic.
- **To-do** — `CREATE_TODO_ITEM | UPDATE_TODO_ITEM | DELETE_TODO_ITEM`.

Still client-only (helpers exist in `api.py`, not yet surfaced as HA actions):
`async_complete_chore`, reward redeem/unredeem, category create/merge. A
`skylight.complete_chore` service is the natural next step.

> ⚠️ Writes are built from observed request shapes but were **not** end-to-end
> tested against a live account (to avoid creating junk on your real calendar).
> Verify create/delete on a throwaway event first.

## Layout

```
custom_components/skylight/
  __init__.py        setup / unload
  api.py             async API client (read + write)
  config_flow.py     UI setup (password or token, frame picker)
  const.py           constants
  coordinator.py     polls the whole household every 5 min
  entity.py          shared base / device info
  calendar.py        calendar entity
  sensor.py          sensors
  todo.py            to-do lists
docs/API.md          full private-API reference
```

## Credits

API surface cross-checked with the community reference
[`mightybandito/Skylight`](https://github.com/mightybandito/Skylight).
