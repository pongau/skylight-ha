# Per-Member Chore Sensors — Design

**Date:** 2026-06-19
**Status:** Approved
**Component:** `custom_components/skylight/sensor.py` (+ one constant in `const.py`)

> This spec uses generic placeholders (`<frame_id>`, `<member>`) rather than any
> real account data.

## Goal

Expose each family member's chores for **today** as a dedicated Home Assistant
sensor, so a wall dashboard can show, per person, how many chores remain and
what they are. One sensor per member, glanceable integer state, full detail in
attributes.

## Target entities

One sensor per family-member profile, following the existing
`has_entity_name` + frame-device naming already used by the points sensors.
With device name `"<FrameName> (<frame_id>)"` and entity name
`"{label} chores"`, Home Assistant derives entity IDs of the form:

```
sensor.<frame_slug>_<member_slug>_chores
```

…one per member profile (the household here has 10). `unique_id =
f"{frame_id}_chores_{profile_id}"`.

### Which profiles get a sensor

Source: `coordinator.data["profiles"]` (categories with
`linked_to_profile == true`). The live account exposes **more** linked profiles
than wanted — the real members **plus a shared `"Family"` profile** that is
structurally identical to a person (same flags, color, picture) and is **not**
wanted.

Neither built-in flag isolates the members:
- All linked profiles → includes the shared `Family` profile.
- `selected_for_chore_chart == true` → drops members who currently have **zero**
  chores but should still get a (0-state) sensor.

Resolution: exclude by label via a new constant in `const.py`:

```python
EXCLUDED_PROFILE_LABELS = {"Family"}
```

A profile gets a sensor when `linked_to_profile` is true **and** its `label` is
not in `EXCLUDED_PROFILE_LABELS`. This deterministically yields exactly the
member set and is trivial to edit later.

Sensors are created for **all members unconditionally** (not gated on having
chores), so members with no chores today still get stable `0`-state entities.

## Data source & mapping

Chores come from `coordinator.data["chores"]` (already fetched each cycle via
`GET /frames/{f}/chores?after&before`, a window of −1d…+30d). Each row is a
**single occurrence** with a composite id (`{group}-{date}-{time}`), its own
`start` date, and its own `completed_on`.

### Per-member, today selection

For a given profile, keep chores where:
1. `relationships.category.data.id == profile_id` — the assignee. Confirmed
   single-valued (no multi-assignment), via the existing `_category_id()` helper.
2. `_is_today(attributes["start"])` — the existing helper, against local "today".

`done = bool(attributes["completed_on"])` (primary). Note the chore `status`
string is `"complete"`/`"pending"` (not `"completed"`); `completed_on` is the
reliable signal and matches the existing aggregate sensor.

Chores are sorted by `attributes["position"]` (Skylight's own ordering).

### Field mapping

| HA attribute | Skylight source | Notes |
|---|---|---|
| state | `total − completed` | incomplete chores remaining today (int, unit `chores`) |
| `display_name` | profile `label` | always present |
| `total` | count of today's chores for member | always |
| `completed` | count with `completed_on` | always |
| `chores[]` | see below | always (possibly empty list) |
| `points_earned` | Σ `reward_points` of completed | only emitted if any chore has `reward_points` |
| `points_possible` | Σ `reward_points` of all today | only emitted if any chore has `reward_points` |

Each `chores[]` item:

| Key | Source | Required | Notes |
|---|---|---|---|
| `name` | `summary` | ✓ | |
| `done` | `bool(completed_on)` | ✓ | |
| `points` | `reward_points` | optional | key omitted when null |
| `due` | formatted `start_time` | optional | `"HH:MM"` 24h → `"8:00 PM"`; key omitted when null |
| `icon` | `emoji_icon` | optional | emoji string |

`due` formatting is defensive: parse `start_time` as `HH:MM` (or a full
datetime) and render `"%-I:%M %p"`; if it will not parse, pass the raw string
through; omit the key when absent.

## Discovery & lifecycle

Extend the existing `_discover()` callback in `async_setup_entry`:

```python
known_members: set[str] = set()
...
for prof in coordinator.data.get("profiles", []):
    pid = str(prof.get("id"))
    label = _attrs(prof).get("label")
    if label in EXCLUDED_PROFILE_LABELS:
        continue
    if pid not in known_members:
        known_members.add(pid)
        new.append(SkylightMemberChoresSensor(coordinator, pid))
```

This mirrors the existing list/points discovery (idempotent via a `known_*`
set, re-run on every coordinator update, registered with
`coordinator.async_add_listener`). All values are read live from
`coordinator.data` in the entity properties, so state stays current with the
5-minute poll and no caching is added.

## Scope decisions

- **Aggregate sensor kept.** The existing `SkylightChoresDueTodaySensor`
  (whole-household incomplete count) is untouched. The per-member sensors are
  additive.
- **One assignee per chore.** Chores assigned to a *label*, to the excluded
  shared profile, or unassigned, do not appear under any member sensor (they
  still count toward the aggregate). Intended.
- **Points emitted only when present.** If `reward_points` is null on all chores
  (as on the validation account), the points attributes are simply not emitted;
  the conditional logic lights them up automatically if points are ever enabled.

## Validated against live data (2026-06-19)

A live pull of the chores + categories endpoints (302 chore occurrences over a
7-day window) confirmed:

- Member link: every chore had exactly one `relationships.category.data.id`
  resolving to a profile id. ✓
- `emoji_icon`: populated on **302/302**. `start_time`: **138/302** (`"HH:MM"`).
  `reward_points > 0`: **0/302**. ✓ matches the mapping above.
- Per-member today counts were sane (small single-digit values; two members had
  0). Only a subset of profiles ever receive chores — confirming the need to
  create every member unconditionally and to exclude the shared profile.

## Out of scope

- Marking chores complete from HA (`async_complete_chore` exists in `api.py` but
  is not surfaced; a future `skylight.complete_chore` service).
- Multi-assignment / "up for grabs" chores.
- Configurable exclusion list via options flow (a constant is sufficient for now).

## Files changed

- `custom_components/skylight/const.py` — add `EXCLUDED_PROFILE_LABELS`.
- `custom_components/skylight/sensor.py` — add `SkylightMemberChoresSensor`,
  extend `_discover()`, add a `_fmt_time()` helper.
