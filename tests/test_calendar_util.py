"""Pure-logic tests for calendar_util. Run: python3.13 tests/test_calendar_util.py

Loaded via importlib so the package's calendar.py (which imports Home Assistant)
never lands on sys.path.
"""
import importlib.util
import os
import sys

_P = os.path.join(os.path.dirname(__file__), "..", "custom_components", "skylight", "calendar_util.py")
_spec = importlib.util.spec_from_file_location("calendar_util", _P)
cu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cu)


def test_clean_rrule_list_with_rrule_only():
    assert cu.clean_rrule(["RRULE:FREQ=WEEKLY"]) == "FREQ=WEEKLY"


def test_clean_rrule_list_with_exdate_and_rrule():
    value = ["EXDATE;TZID=America/Phoenix:20250718T070000,20250725T070000", "RRULE:FREQ=WEEKLY"]
    assert cu.clean_rrule(value) == "FREQ=WEEKLY"


def test_clean_rrule_complex_byday():
    assert cu.clean_rrule(["RRULE:FREQ=WEEKLY;BYDAY=FR,MO,TH,TU,WE"]) == "FREQ=WEEKLY;BYDAY=FR,MO,TH,TU,WE"


def test_clean_rrule_none_and_empty():
    assert cu.clean_rrule(None) is None
    assert cu.clean_rrule([]) is None
    assert cu.clean_rrule("") is None


def test_clean_rrule_bare_string_with_prefix():
    assert cu.clean_rrule("RRULE:FREQ=DAILY") == "FREQ=DAILY"


def test_clean_rrule_bare_string_without_prefix():
    assert cu.clean_rrule("FREQ=DAILY;INTERVAL=2") == "FREQ=DAILY;INTERVAL=2"


def test_clean_rrule_exdate_only_returns_none():
    assert cu.clean_rrule(["EXDATE;TZID=America/Phoenix:20250718T070000"]) is None


def test_clean_rrule_ignores_non_string_items():
    assert cu.clean_rrule([None, 123, "RRULE:FREQ=MONTHLY"]) == "FREQ=MONTHLY"


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
