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

from datetime import date  # noqa: E402


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
