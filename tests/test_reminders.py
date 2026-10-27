"""整点报时与久坐提醒调度测试。"""

from __future__ import annotations

from datetime import datetime, timedelta

from leiyu_pet.reminders import BREAK, HOURLY, ReminderPlanner, clamp_break_minutes, reminder_text


def at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 10, 27, hour, minute, second)


def test_hourly_fires_once_per_hour() -> None:
    planner = ReminderPlanner(hourly=True)
    assert planner.poll(at(10, 0)) == [HOURLY]
    assert planner.poll(at(10, 0, 30)) == []
    assert planner.poll(at(10, 30)) == []
    assert planner.poll(at(11, 0)) == [HOURLY]


def test_hourly_ignores_non_zero_minute() -> None:
    planner = ReminderPlanner(hourly=True)
    assert planner.poll(at(10, 5)) == []


def test_break_reminder_uses_baseline_then_interval() -> None:
    planner = ReminderPlanner(break_minutes=30)
    start = at(9, 0)
    assert planner.poll(start) == []
    assert planner.poll(start + timedelta(minutes=29)) == []
    assert planner.poll(start + timedelta(minutes=30)) == [BREAK]
    assert planner.poll(start + timedelta(minutes=45)) == []
    assert planner.poll(start + timedelta(minutes=60)) == [BREAK]


def test_disabling_break_reminder_resets_baseline() -> None:
    planner = ReminderPlanner(break_minutes=30)
    planner.poll(at(9, 0))
    planner.break_minutes = 0
    assert planner.poll(at(9, 30)) == []
    planner.break_minutes = 30
    assert planner.poll(at(9, 31)) == []  # 重新建立基准
    assert planner.poll(at(10, 1)) == [BREAK]


def test_both_reminders_can_fire_together() -> None:
    planner = ReminderPlanner(hourly=True, break_minutes=30)
    planner.poll(at(9, 0))
    assert planner.poll(at(10, 0)) == [HOURLY, BREAK]


def test_clamp_and_text() -> None:
    assert clamp_break_minutes(-5) == 0
    assert clamp_break_minutes(999) == 240
    assert clamp_break_minutes("x") == 0
    assert "10 点整" in reminder_text(HOURLY, at(10, 0), 0)
    assert "45 分钟" in reminder_text(BREAK, at(10, 0), 45)
