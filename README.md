# Skylight Calendar — Home Assistant integration

A custom Home Assistant integration that bridges your **Skylight family
calendar** (`ourskylight.com`) into Home Assistant.

It is **read-only** today (exposes your household's data as HA entities), but
the underlying API client is full read/write, so adding write features later
(create events, complete chores, edit lists) is a small step.

> ⚠️ **Unofficial.** Skylight has no public API for the family-calendar
> product. This talks to the private app API, reverse-engineered and documented
> in [`docs/API.md`](docs/API.md). It may break if Skylight changes things. Use
> only with your own account.

## What you get

One **device per Skylight frame**, with:

- 📅 **Calendar** entity — all events, queryable by Lovelace calendar cards and
  automations (`calendar.skylight_calendar`).
- 🔢 **Sensors**
  - `Events today` (+ list of titles)
  - `Chores due today` (+ list)
  - One **points** sensor per profile (if rewards are enabled)
  - One **list** sensor per Skylight list (pending item count + items)
- ✅ **To-do lists** — each Skylight list (shopping / to-do) as a read-only HA
  to-do list.

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

Choose one of:

- **Email & password** (recommended) — stored in HA and used to fetch
  short-lived (2h) access tokens, auto-refreshed by re-login.
- **Paste an access token** — capture a `Bearer` token from the app (see
  [`docs/API.md`](docs/API.md)). No credentials stored, but the token expires
  in ~2h and won't auto-refresh.

Then pick which **frame** (calendar) to add. Add the integration again to add
more frames.

## Security

- Credentials/tokens live in HA's encrypted config-entry store — never in code
  or logs.
- ⚠️ A Skylight password grants **full account access** (no scoped keys). Treat
  it accordingly. Details in [`docs/API.md`](docs/API.md#security-note).

## Making it read/write (later)

`api.py` already implements `async_create_calendar_event`,
`async_complete_chore`, `async_create_list_item`, etc. To expose them:

- Add `CalendarEntityFeature.CREATE_EVENT…` to the calendar entity and
  implement `async_create_event` / `async_delete_event`.
- Add `TodoListEntityFeature.CREATE_TODO_ITEM…` to the to-do entity.

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
