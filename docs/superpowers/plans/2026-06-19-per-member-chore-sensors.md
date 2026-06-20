# Per-Member Chore Sensors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one Home Assistant sensor per Skylight family-member profile that reports today's incomplete-chore count as its state and the full chore breakdown (name, done, optional points/due/icon) as attributes.

**Architecture:** All data-shaping logic lives in a new **pure module** `chore_summary.py` (standard library only, no Home Assistant imports) so it is unit-testable with plain `python3.13`. A thin `SkylightMemberChoresSensor` entity in the existing `sensor.py` reads live from the coordinator and delegates to that module. Discovery is added to the existing `_discover()` callback; a `Family`-style shared profile is excluded via a constant.

**Tech Stack:** Python 3.12+ (Home Assistant runtime; verify locally with `python3.13`), Home Assistant custom-integration `SensorEntity` + `DataUpdateCoordinator`. Tests are plain-`assert` Python (no pytest dependency required), runnable via `python3.13 tests/test_chore_summary.py`.

**Repo note:** This is a **public** repo. All test fixtures and plan examples use **synthetic** data only — no real member names, frame ids, or chore text.

**Local verification commands:**
- Pure-logic tests: `python3.13 tests/test_chore_summary.py` (exit 0 = pass)
- Compile check (HA-dependent files can't run locally, but must parse): `python3.13 -m py_compile custom_components/skylight/*.py`

---

## File Structure

- **Create** `custom_components/skylight/chore_summary.py` — pure helpers: `fmt_time()`, `category_id()`, `is_on_date()`, `build_member_summary()`. No HA imports.
- **Create** `tests/test_chore_summary.py` — plain-assert tests for the pure module.
- **Modify** `custom_components/skylight/const.py` — add `EXCLUDED_PROFILE_LABELS`.
- **Modify** `custom_components/skylight/sensor.py` — add `SkylightMemberChoresSensor`; extend `_discover()`; new imports.

> **DRY note:** `chore_summary.py` defines its own tiny `_attrs`/`category_id` rather than importing from `sensor.py`, because `sensor.py` imports Home Assistant and must not be importable in pure tests. The duplication is a few trivial lines and is the price of an HA-free, locally-testable core. Do **not** move the existing `sensor.py` helpers.

---

## Task 1: Pure helper `fmt_time`

**Files:**
- Create: `custom_components/skylight/chore_summary.py`
- Test: `tests/test_chore_summary.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_chore_summary.py`:

```python
"""Pure-logic tests for chore_summary. Run: python3.13 tests/test_chore_summary.py

chore_summary is loaded directly from its file path via importlib so the
package's sibling modules (calendar.py, sensor.py, ...) never land on sys.path
and shadow stdlib modules like ``calendar``.
"""
import importlib.util
import os
import sys

_MODULE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "skylight", "chore_summary.py"
)
_spec = importlib.util.spec_from_file_location("chore_summary", _MODULE_PATH)
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)


def test_fmt_time_24h_to_12h():
    assert cs.fmt_time("20:00") == "8:00 PM"
    assert cs.fmt_time("09:05") == "9:05 AM"
    assert cs.fmt_time("00:30") == "12:30 AM"
    assert cs.fmt_time("12:00") == "12:00 PM"
    assert cs.fmt_time("10:15") == "10:15 AM"


def test_fmt_time_absent_returns_none():
    assert cs.fmt_time(None) is None
    assert cs.fmt_time("") is None


def test_fmt_time_unparseable_passes_through():
    assert cs.fmt_time("whenever") == "whenever"


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.13 tests/test_chore_summary.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'chore_summary'` (file not created yet).

- [ ] **Step 3: Write minimal implementation**

Create `custom_components/skylight/chore_summary.py`:

```python
"""Pure helpers for per-member chore summaries.

No Home Assistant imports — standard library only — so this module is unit
testable with a bare Python interpreter. The Home Assistant entity in
``sensor.py`` is a thin wrapper over ``build_member_summary``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def fmt_time(start_time: str | None) -> str | None:
    """Render a Skylight chore time as a 12-hour string, e.g. '20:00' -> '8:00 PM'.

    Accepts 'HH:MM', 'HH:MM:SS', or a full ISO datetime. Returns None when
    absent; passes unparseable input through unchanged.
    """
    if not start_time:
        return None
    text = str(start_time).strip()
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%I:%M %p").lstrip("0")
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return text
```

> Note: `"%I:%M %p"` zero-pads the hour (`08:00 PM`); `.lstrip("0")` strips the
> single leading zero (`8:00 PM`) and never touches `10/11/12` hours. This avoids
> the non-portable `%-I` directive.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.13 tests/test_chore_summary.py`
Expected: PASS — `3/3 passed`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add custom_components/skylight/chore_summary.py tests/test_chore_summary.py
git commit -m "feat(chores): pure fmt_time helper for chore due times"
```

---

## Task 2: Pure helpers `category_id` and `is_on_date`

**Files:**
- Modify: `custom_components/skylight/chore_summary.py`
- Test: `tests/test_chore_summary.py`

- [ ] **Step 1: Write the failing tests**

Append these test functions to `tests/test_chore_summary.py` (before the `if __name__` block):

```python
def test_category_id_from_relationship():
    chore = {"relationships": {"category": {"data": {"id": "42", "type": "category"}}}}
    assert cs.category_id(chore) == "42"


def test_category_id_fallback_to_attribute():
    chore = {"attributes": {"category_id": 7}}
    assert cs.category_id(chore) == "7"


def test_category_id_missing_returns_none():
    assert cs.category_id({"relationships": {"category": {"data": None}}}) is None
    assert cs.category_id({}) is None


def test_is_on_date_matches_date_prefix():
    assert cs.is_on_date("2026-06-19", date(2026, 6, 19)) is True
    assert cs.is_on_date("2026-06-19T20:00:00", date(2026, 6, 19)) is True
    assert cs.is_on_date("2026-06-18", date(2026, 6, 19)) is False
    assert cs.is_on_date(None, date(2026, 6, 19)) is False
    assert cs.is_on_date("garbage", date(2026, 6, 19)) is False
```

Add `from datetime import date` to the test file's imports (top, after the importlib bootstrap block):

```python
from datetime import date  # noqa: E402
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.13 tests/test_chore_summary.py`
Expected: FAIL — `AttributeError: module 'chore_summary' has no attribute 'category_id'`.

- [ ] **Step 3: Write minimal implementation**

Append to `custom_components/skylight/chore_summary.py`:

```python
def _attrs(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("attributes", {}) if isinstance(item, dict) else {}


def category_id(chore: dict[str, Any]) -> str | None:
    """The assigned profile/category id for a chore, or None."""
    rel = chore.get("relationships", {}) if isinstance(chore, dict) else {}
    data = (rel.get("category") or {}).get("data") if isinstance(rel, dict) else None
    if isinstance(data, dict) and data.get("id") is not None:
        return str(data["id"])
    attr = _attrs(chore)
    if attr.get("category_id") is not None:
        return str(attr["category_id"])
    return None


def is_on_date(value: str | None, day: date) -> bool:
    """True if an ISO date/datetime string falls on ``day`` (date portion only)."""
    if not value:
        return False
    try:
        return date.fromisoformat(str(value)[:10]) == day
    except ValueError:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.13 tests/test_chore_summary.py`
Expected: PASS — `8/8 passed`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add custom_components/skylight/chore_summary.py tests/test_chore_summary.py
git commit -m "feat(chores): category_id + is_on_date pure helpers"
```

---

## Task 3: Pure core `build_member_summary`

**Files:**
- Modify: `custom_components/skylight/chore_summary.py`
- Test: `tests/test_chore_summary.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chore_summary.py` (before the `if __name__` block). Note the synthetic fixture — no real data:

```python
def _chore(cat, start, summary, *, done=False, start_time=None, icon=None, points=None, position=0):
    attrs = {
        "summary": summary,
        "start": start,
        "completed_on": start if done else None,
        "start_time": start_time,
        "emoji_icon": icon,
        "reward_points": points,
        "position": position,
    }
    return {
        "attributes": attrs,
        "relationships": {"category": {"data": {"id": str(cat), "type": "category"}}},
    }


DAY = date(2026, 6, 19)


def test_summary_filters_by_member_and_day():
    chores = [
        _chore("1", "2026-06-19", "Mine today"),
        _chore("2", "2026-06-19", "Other member"),
        _chore("1", "2026-06-18", "Mine yesterday"),
    ]
    out = cs.build_member_summary(chores, "1", "Alex", DAY)
    names = [c["name"] for c in out["attributes"]["chores"]]
    assert names == ["Mine today"]
    assert out["attributes"]["total"] == 1
    assert out["attributes"]["display_name"] == "Alex"


def test_summary_state_is_incomplete_remaining():
    chores = [
        _chore("1", "2026-06-19", "A", done=True, position=1),
        _chore("1", "2026-06-19", "B", done=False, position=2),
        _chore("1", "2026-06-19", "C", done=False, position=3),
    ]
    out = cs.build_member_summary(chores, "1", "Alex", DAY)
    assert out["state"] == 2
    assert out["attributes"]["total"] == 3
    assert out["attributes"]["completed"] == 1


def test_summary_sorted_by_position():
    chores = [
        _chore("1", "2026-06-19", "third", position=30),
        _chore("1", "2026-06-19", "first", position=10),
        _chore("1", "2026-06-19", "second", position=20),
    ]
    out = cs.build_member_summary(chores, "1", "Alex", DAY)
    assert [c["name"] for c in out["attributes"]["chores"]] == ["first", "second", "third"]


def test_summary_optional_keys_omitted_when_null():
    chores = [_chore("1", "2026-06-19", "Plain")]
    item = cs.build_member_summary(chores, "1", "Alex", DAY)["attributes"]["chores"][0]
    assert item == {"name": "Plain", "done": False}
    assert "points" not in item and "due" not in item and "icon" not in item


def test_summary_optional_keys_present_when_set():
    chores = [_chore("1", "2026-06-19", "Rich", start_time="20:00", icon="X", points=5)]
    item = cs.build_member_summary(chores, "1", "Alex", DAY)["attributes"]["chores"][0]
    assert item["due"] == "8:00 PM"
    assert item["icon"] == "X"
    assert item["points"] == 5


def test_summary_points_totals_only_when_present():
    no_points = cs.build_member_summary([_chore("1", "2026-06-19", "A")], "1", "Alex", DAY)
    assert "points_earned" not in no_points["attributes"]
    assert "points_possible" not in no_points["attributes"]

    with_points = cs.build_member_summary(
        [
            _chore("1", "2026-06-19", "A", done=True, points=5),
            _chore("1", "2026-06-19", "B", done=False, points=3),
        ],
        "1",
        "Alex",
        DAY,
    )
    assert with_points["attributes"]["points_earned"] == 5
    assert with_points["attributes"]["points_possible"] == 8


def test_summary_member_with_no_chores():
    out = cs.build_member_summary([], "1", "Alex", DAY)
    assert out["state"] == 0
    assert out["attributes"] == {
        "display_name": "Alex",
        "total": 0,
        "completed": 0,
        "chores": [],
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.13 tests/test_chore_summary.py`
Expected: FAIL — `AttributeError: module 'chore_summary' has no attribute 'build_member_summary'`.

- [ ] **Step 3: Write minimal implementation**

Append to `custom_components/skylight/chore_summary.py`:

```python
def build_member_summary(
    chores: list[dict[str, Any]],
    profile_id: str,
    label: str | None,
    day: date,
) -> dict[str, Any]:
    """State + attributes for one member's chores on ``day``.

    Returns ``{"state": int, "attributes": {...}}`` where state is the number of
    incomplete chores remaining today.
    """
    mine = [
        c
        for c in chores
        if category_id(c) == str(profile_id) and is_on_date(_attrs(c).get("start"), day)
    ]
    mine.sort(key=lambda c: _attrs(c).get("position") or 0)

    items: list[dict[str, Any]] = []
    completed = 0
    points_earned = 0
    points_possible = 0
    any_points = False

    for chore in mine:
        attr = _attrs(chore)
        done = bool(attr.get("completed_on"))
        if done:
            completed += 1

        item: dict[str, Any] = {"name": attr.get("summary"), "done": done}

        points = attr.get("reward_points")
        if points is not None:
            any_points = True
            item["points"] = points
            points_possible += points
            if done:
                points_earned += points

        due = fmt_time(attr.get("start_time"))
        if due is not None:
            item["due"] = due

        icon = attr.get("emoji_icon")
        if icon:
            item["icon"] = icon

        items.append(item)

    total = len(mine)
    attributes: dict[str, Any] = {
        "display_name": label,
        "total": total,
        "completed": completed,
        "chores": items,
    }
    if any_points:
        attributes["points_earned"] = points_earned
        attributes["points_possible"] = points_possible

    return {"state": total - completed, "attributes": attributes}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.13 tests/test_chore_summary.py`
Expected: PASS — `14/14 passed`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add custom_components/skylight/chore_summary.py tests/test_chore_summary.py
git commit -m "feat(chores): build_member_summary core logic + tests"
```

---

## Task 4: Constant + Home Assistant entity wiring

**Files:**
- Modify: `custom_components/skylight/const.py`
- Modify: `custom_components/skylight/sensor.py`

> This task touches HA-importing code, which **cannot run** outside Home Assistant. Verification is `py_compile` (it must parse) plus careful review; runtime behavior is confirmed on the user's HA in Task 5.

- [ ] **Step 1: Add the exclusion constant**

In `custom_components/skylight/const.py`, append:

```python
# Linked profiles that are NOT real people and should not get per-member
# sensors (shared/household categories). Matched against the profile label.
EXCLUDED_PROFILE_LABELS = {"Family"}
```

- [ ] **Step 2: Add imports to `sensor.py`**

In `custom_components/skylight/sensor.py`, add to the existing local imports block (which already imports `SkylightConfigEntry`, `SkylightCoordinator`, `SkylightEntity`):

```python
from .chore_summary import build_member_summary
from .const import EXCLUDED_PROFILE_LABELS
```

- [ ] **Step 3: Register member sensors in `_discover()`**

In `async_setup_entry`, add a tracking set alongside the existing `known_lists` / `known_profiles`:

```python
    known_members: set[str] = set()
```

Then inside the `_discover()` callback, after the existing profile-points loop, add:

```python
        for prof in coordinator.data.get("profiles", []):
            if _attrs(prof).get("label") in EXCLUDED_PROFILE_LABELS:
                continue
            pid = str(prof.get("id"))
            if pid not in known_members:
                known_members.add(pid)
                new.append(SkylightMemberChoresSensor(coordinator, pid))
```

- [ ] **Step 4: Add the entity class**

Append to `custom_components/skylight/sensor.py`:

```python
class SkylightMemberChoresSensor(SkylightEntity, SensorEntity):
    """One family member's chores for today.

    State is the number of incomplete chores remaining today; the full
    breakdown is in attributes. See chore_summary.build_member_summary.
    """

    _attr_icon = "mdi:broom"
    _attr_native_unit_of_measurement = "chores"

    def __init__(self, coordinator: SkylightCoordinator, profile_id: str) -> None:
        super().__init__(coordinator)
        self._profile_id = profile_id
        self._attr_unique_id = f"{self._frame_id}_chores_{profile_id}"

    def _profile(self) -> dict[str, Any]:
        for prof in self.coordinator.data.get("profiles", []):
            if str(prof.get("id")) == self._profile_id:
                return prof
        return {}

    @property
    def name(self) -> str:
        label = _attrs(self._profile()).get("label") or f"Profile {self._profile_id}"
        return f"{label} chores"

    def _summary(self) -> dict[str, Any]:
        return build_member_summary(
            self.coordinator.data.get("chores", []),
            self._profile_id,
            _attrs(self._profile()).get("label"),
            dt_util.now().date(),
        )

    @property
    def native_value(self) -> int:
        return self._summary()["state"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._summary()["attributes"]
```

- [ ] **Step 5: Compile-check all modules**

Run: `python3.13 -m py_compile custom_components/skylight/*.py`
Expected: no output, exit 0 (all modules parse).

- [ ] **Step 6: Re-run pure tests (guard against accidental breakage)**

Run: `python3.13 tests/test_chore_summary.py`
Expected: PASS — `14/14 passed`.

- [ ] **Step 7: Commit**

```bash
git add custom_components/skylight/const.py custom_components/skylight/sensor.py
git commit -m "feat(chores): per-member chore sensors (SkylightMemberChoresSensor)"
```

---

## Task 5: Final verification + on-HA confirmation

**Files:** none (verification only)

- [ ] **Step 1: Full local check**

Run:
```bash
python3.13 -m py_compile custom_components/skylight/*.py && python3.13 tests/test_chore_summary.py
```
Expected: compile clean, `14/14 passed`, exit 0.

- [ ] **Step 2: Deploy to Home Assistant**

Update the integration on the user's HA (HACS custom repo → redownload the branch, or Samba/SSH copy `custom_components/skylight/`), then restart HA.

- [ ] **Step 3: Confirm entities**

In Developer Tools → States, filter for `_chores`. Expected: one `sensor.<frame_slug>_<member_slug>_chores` per member (10 on the validation account), no sensor for the excluded shared profile, and the existing aggregate `chores_due_today` still present.

- [ ] **Step 4: Confirm data**

Pick a member known to have chores today. Expected: integer state = incomplete remaining; attributes include `display_name`, `total`, `completed`, and a `chores` list whose items carry `name`, `done`, an `icon`, and a `due` time where the chore has one. A member with no chores today reads `0` with an empty `chores` list.

- [ ] **Step 5: Report results**

Note any mismatch (wrong count, missing member, wrong done state, bad due format) for follow-up. If the shared profile's label is not literally `Family` on this account, adjust `EXCLUDED_PROFILE_LABELS` in `const.py`.

---

## Self-Review

**Spec coverage:**
- 10 entities, one per member, existing slug pattern → Task 4 (entity `name = "{label} chores"`, discovery loop). ✓
- State = incomplete remaining → Task 3 (`state = total - completed`), Task 4 (`native_value`). ✓
- Attributes `display_name`/`total`/`completed`/`chores` always; `points_earned`/`points_possible` conditional → Task 3. ✓
- Per-chore `name`/`done` required; `points`/`due`/`icon` optional/omitted-when-null → Task 3. ✓
- `due` "HH:MM" → "8:00 PM" → Task 1. ✓
- Member link via `relationships.category`; today filter; done via `completed_on`; sort by `position` → Tasks 2-3. ✓
- Exclude `Family`; create all members unconditionally; keep aggregate sensor → Task 4. ✓

**Placeholder scan:** No TBD/TODO; every code step contains complete code; no "add error handling" hand-waves. ✓

**Type consistency:** `build_member_summary(chores, profile_id, label, day)` returns `{"state": int, "attributes": dict}` — consumed identically in Task 4 (`_summary()["state"]`, `_summary()["attributes"]`). Helper names `fmt_time`/`category_id`/`is_on_date`/`_attrs` match across module and tests. ✓
