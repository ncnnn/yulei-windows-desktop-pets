"""番茄钟状态机测试。"""

from __future__ import annotations

from datetime import datetime, timedelta

from leiyu_pet.pomodoro import BREAK_DONE, FOCUS_DONE, Pomodoro, PomodoroStage, clamp_minutes


def at(minute: int = 0) -> datetime:
    return datetime(2026, 10, 27, 9, minute)


def test_start_enters_focus_with_deadline() -> None:
    timer = Pomodoro(focus_minutes=25)
    assert timer.start(at()) is PomodoroStage.FOCUS
    assert timer.active is True
    assert timer.remaining_seconds(at()) == 25 * 60


def test_tick_before_deadline_does_nothing() -> None:
    timer = Pomodoro(focus_minutes=25)
    timer.start(at())
    assert timer.tick(at() + timedelta(minutes=24)) is None
    assert timer.stage is PomodoroStage.FOCUS


def test_focus_then_break_then_done() -> None:
    timer = Pomodoro(focus_minutes=25, break_minutes=5)
    timer.start(at())
    assert timer.tick(at() + timedelta(minutes=25)) == FOCUS_DONE
    assert timer.stage is PomodoroStage.BREAK
    assert timer.tick(at() + timedelta(minutes=29)) is None
    assert timer.tick(at() + timedelta(minutes=30)) == BREAK_DONE
    assert timer.stage is PomodoroStage.IDLE
    assert timer.active is False


def test_start_while_active_keeps_stage() -> None:
    timer = Pomodoro()
    timer.start(at())
    deadline = timer.deadline
    assert timer.start(at(5)) is PomodoroStage.FOCUS
    assert timer.deadline == deadline


def test_stop_and_remaining_text() -> None:
    timer = Pomodoro(focus_minutes=25)
    timer.start(at())
    assert timer.remaining_text(at() + timedelta(minutes=1)) == "24:00"
    timer.stop()
    assert timer.active is False
    assert timer.remaining_text(at()) == "00:00"


def test_clamp_minutes() -> None:
    assert clamp_minutes(0) == 1
    assert clamp_minutes(999) == 180
    assert clamp_minutes("x") == 1
