"""提醒中枢：整点/久坐/番茄钟的信号与免打扰门禁。"""

from __future__ import annotations

from datetime import datetime, timedelta

from leiyu_pet.assistant import PetAssistant


def at(minute: int = 0, hour: int = 10) -> datetime:
    return datetime(2026, 10, 27, hour, minute)


def test_hourly_notice_is_emitted(qapp) -> None:
    assistant = PetAssistant()
    assistant.configure(hourly=True, break_minutes=0, focus_minutes=25, rest_minutes=5)
    seen: list[str] = []
    assistant.notice.connect(seen.append)
    try:
        messages = assistant.poll(at(0))
        assert messages and "10 点整" in messages[0]
        assert seen == messages
    finally:
        assistant.stop_polling()


def test_quiet_hours_suppress_notices_but_keep_state(qapp) -> None:
    assistant = PetAssistant()
    assistant.configure(hourly=True, break_minutes=0, focus_minutes=25, rest_minutes=5)
    assistant.set_quiet_checker(lambda: True)
    seen: list[str] = []
    assistant.notice.connect(seen.append)
    try:
        assert assistant.poll(at(0)) == []
        assert seen == []
        assert assistant.planner.last_hour == 10
    finally:
        assistant.stop_polling()


def test_pomodoro_start_stop_and_status(qapp) -> None:
    assistant = PetAssistant()
    try:
        assert assistant.pomodoro_status() == "未开始"
        assert assistant.start_pomodoro() is True
        assert assistant.pomodoro_active is True
        assert assistant.start_pomodoro() is False
        assert assistant.pomodoro_status().startswith("专注中")
        assistant.stop_pomodoro()
        assert assistant.pomodoro_status() == "未开始"
    finally:
        assistant.stop_polling()


def test_pomodoro_transition_emits_notice(qapp) -> None:
    assistant = PetAssistant()
    assistant.configure(hourly=False, break_minutes=0, focus_minutes=25, rest_minutes=5)
    seen: list[str] = []
    assistant.notice.connect(seen.append)
    try:
        assistant.pomodoro.start(at())
        messages = assistant.poll(at() + timedelta(minutes=25))
        assert messages and "休息" in messages[0]
        assert assistant.pomodoro.remaining_text(at() + timedelta(minutes=25)) == "05:00"
        assert assistant.poll(at() + timedelta(minutes=30))[0].startswith("休息结束")
        assert assistant.pomodoro_active is False
    finally:
        assistant.stop_polling()
