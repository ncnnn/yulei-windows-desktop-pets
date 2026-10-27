"""整点报时与久坐提醒的纯逻辑调度。

只根据「当前时间」判断该不该提醒，不依赖 Qt 定时器；真正的轮询由运行时用
``QTimer`` 驱动，这样逻辑可以单独测试，也不会在无窗口环境里卡住。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

HOURLY = "hourly"
BREAK = "break"

#: 久坐提醒的可选间隔（分钟），0 表示关闭。
BREAK_PRESETS = (0, 30, 45, 60, 90)


def clamp_break_minutes(value: int) -> int:
    """把久坐间隔夹到 0..240，非法值按 0（关闭）处理。"""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return 0
    return min(max(minutes, 0), 240)


def reminder_text(kind: str, now: datetime, break_minutes: int) -> str:
    """生成提醒文案，语气保持和桌宠一致（短、口语）。"""
    if kind == HOURLY:
        return f"{now.hour} 点整了，起来喝口水吧。"
    return f"已经坐了 {clamp_break_minutes(break_minutes)} 分钟，动一动再继续。"


@dataclass(slots=True)
class ReminderPlanner:
    """记录上次提醒时间，决定这一轮该发哪些提醒。"""

    hourly: bool = False
    break_minutes: int = 0
    last_hour: int | None = None
    last_break: datetime | None = None

    def poll(self, now: datetime) -> list[str]:
        """返回本次触发的提醒类型列表（可能同时有整点和久坐）。"""
        fired: list[str] = []
        if self.hourly and now.minute == 0 and self.last_hour != now.hour:
            self.last_hour = now.hour
            fired.append(HOURLY)

        minutes = clamp_break_minutes(self.break_minutes)
        if minutes <= 0:
            self.last_break = None
        elif self.last_break is None:
            # 第一次轮询只记录基准点，避免刚启动就立刻提醒。
            self.last_break = now
        elif now - self.last_break >= timedelta(minutes=minutes):
            self.last_break = now
            fired.append(BREAK)
        return fired

    def reset(self) -> None:
        self.last_hour = None
        self.last_break = None
