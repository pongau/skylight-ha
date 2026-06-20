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
