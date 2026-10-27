"""番茄钟状态机：专注 → 休息 → 结束。

时间推进由调用方传入 ``now``，因此可以注入固定时间做单测，不依赖真实等待。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

FOCUS_DONE = "focus_done"
BREAK_DONE = "break_done"

#: 设置页/菜单里提供的专注时长（分钟）。
FOCUS_PRESETS = (15, 25, 45, 60)
BREAK_PRESETS = (5, 10, 15)


class PomodoroStage(StrEnum):
    IDLE = "idle"
    FOCUS = "focus"
    BREAK = "break"


def clamp_minutes(value: int, *, low: int = 1, high: int = 180) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return low
    return min(max(minutes, low), high)


@dataclass(slots=True)
class Pomodoro:
    focus_minutes: int = 25
    break_minutes: int = 5
    stage: PomodoroStage = PomodoroStage.IDLE
    deadline: datetime | None = None

    @property
    def active(self) -> bool:
        return self.stage is not PomodoroStage.IDLE

    def start(self, now: datetime) -> PomodoroStage:
        """开始一轮专注；已在运行时保持原状。"""
        if self.active:
            return self.stage
        self.focus_minutes = clamp_minutes(self.focus_minutes)
        self.break_minutes = clamp_minutes(self.break_minutes, high=60)
        self.stage = PomodoroStage.FOCUS
        self.deadline = now + timedelta(minutes=self.focus_minutes)
        return self.stage

    def stop(self) -> None:
        self.stage = PomodoroStage.IDLE
        self.deadline = None

    def tick(self, now: datetime) -> str | None:
        """到点则推进阶段并返回事件名；未到点返回 ``None``。"""
        if self.deadline is None or not self.active:
            return None
        if now < self.deadline:
            return None
        if self.stage is PomodoroStage.FOCUS:
            self.stage = PomodoroStage.BREAK
            self.deadline = now + timedelta(minutes=clamp_minutes(self.break_minutes, high=60))
            return FOCUS_DONE
        self.stop()
        return BREAK_DONE

    def remaining_seconds(self, now: datetime) -> int:
        if self.deadline is None:
            return 0
        return max(0, int((self.deadline - now).total_seconds()))

    def remaining_text(self, now: datetime) -> str:
        """``"24:59"`` 形式的倒计时，便于托盘提示。"""
        remaining = self.remaining_seconds(now)
        return f"{remaining // 60:02d}:{remaining % 60:02d}"
