"""免打扰时段纯逻辑测试。"""

from __future__ import annotations

from datetime import datetime

from leiyu_pet.quiet_hours import in_quiet_hours, normalize_hhmm, parse_hhmm


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 27, hour, minute)


def test_parse_hhmm_valid_and_invalid() -> None:
    assert parse_hhmm("00:00") == 0
    assert parse_hhmm("23:59") == 1439
    assert parse_hhmm("8:5") == 485
    for bad in ("", "24:00", "12:60", "abc", "12-30", "12:30:00"):
        assert parse_hhmm(bad) is None


def test_normalize_falls_back() -> None:
    assert normalize_hhmm("7:5", "23:00") == "07:05"
    assert normalize_hhmm("oops", "23:00") == "23:00"
    assert normalize_hhmm("oops", "bad") == "00:00"


def test_same_day_range() -> None:
    assert in_quiet_hours(at(9, 0), "09:00", "17:00") is True
    assert in_quiet_hours(at(16, 59), "09:00", "17:00") is True
    assert in_quiet_hours(at(17, 0), "09:00", "17:00") is False
    assert in_quiet_hours(at(8, 59), "09:00", "17:00") is False


def test_cross_midnight_range() -> None:
    assert in_quiet_hours(at(23, 30), "23:00", "08:00") is True
    assert in_quiet_hours(at(0, 0), "23:00", "08:00") is True
    assert in_quiet_hours(at(7, 59), "23:00", "08:00") is True
    assert in_quiet_hours(at(8, 0), "23:00", "08:00") is False
    assert in_quiet_hours(at(12, 0), "23:00", "08:00") is False


def test_invalid_or_empty_range_is_never_quiet() -> None:
    assert in_quiet_hours(at(12, 0), "bad", "08:00") is False
    assert in_quiet_hours(at(12, 0), "23:00", "bad") is False
    assert in_quiet_hours(at(12, 0), "08:00", "08:00") is False
