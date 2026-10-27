"""提醒中枢：整点报时、久坐提醒与番茄钟。

纯逻辑在 ``reminders`` / ``pomodoro`` 里，本模块只负责按时间轮询并用信号把
「该说什么」交给主程序；免打扰时段通过注入的检查函数决定要不要出声。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from .pomodoro import BREAK_DONE, FOCUS_DONE, Pomodoro, PomodoroStage, clamp_minutes
from .reminders import ReminderPlanner, reminder_text

POLL_INTERVAL_MS = 30_000
#: 番茄钟倒计时刷新间隔：1 秒，用于在桌宠气泡上实时显示剩余时间。
COUNTDOWN_INTERVAL_MS = 1_000


class PetAssistant(QObject):
    notice = Signal(str)
    pomodoro_changed = Signal(str)
    #: 番茄钟倒计时文本；空字符串表示计时结束/未开始，调用方应清掉常驻气泡。
    countdown = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.planner = ReminderPlanner()
        self.pomodoro = Pomodoro()
        self._quiet: Callable[[], bool] = lambda: False
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.poll)
        self._timer.start()
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(COUNTDOWN_INTERVAL_MS)
        self._countdown_timer.timeout.connect(self._emit_countdown)

    def set_quiet_checker(self, checker: Callable[[], bool]) -> None:
        """注入免打扰判断（读当前配置，改动即时生效）。"""
        self._quiet = checker

    def stop_polling(self) -> None:
        self._timer.stop()
        self._countdown_timer.stop()

    def configure(
        self,
        *,
        hourly: bool,
        break_minutes: int,
        focus_minutes: int,
        rest_minutes: int,
    ) -> None:
        self.planner.hourly = bool(hourly)
        self.planner.break_minutes = int(break_minutes)
        if not self.planner.hourly:
            self.planner.last_hour = None
        self.pomodoro.focus_minutes = clamp_minutes(focus_minutes)
        self.pomodoro.break_minutes = clamp_minutes(rest_minutes, high=60)

    def poll(self, now: datetime | None = None) -> list[str]:
        """轮询一次；返回本轮发出的提醒文案（便于测试）。"""
        current = now or datetime.now()
        quiet = bool(self._quiet())
        messages: list[str] = []

        for kind in self.planner.poll(current):
            messages.append(reminder_text(kind, current, self.planner.break_minutes))

        event = self.pomodoro.tick(current)
        if event == FOCUS_DONE:
            self.pomodoro_changed.emit("休息")
            # 阶段切换立刻刷新气泡，不必等下一次 1 秒 tick。
            if not self._countdown_timer.isActive():
                self._countdown_timer.start()
            self._emit_countdown()
            messages.append(
                f"专注 {self.pomodoro.focus_minutes} 分钟结束，"
                f"休息 {self.pomodoro.break_minutes} 分钟吧。"
            )
        elif event == BREAK_DONE:
            self.pomodoro_changed.emit("结束")
            self._countdown_timer.stop()
            self.countdown.emit("")
            messages.append("休息结束，回来继续吧。")

        if quiet:
            # 免打扰期间只推进状态，不发声、不弹气泡。
            return []
        for message in messages:
            self.notice.emit(message)
        return messages

    def _emit_countdown(self) -> None:
        if not self.pomodoro.active:
            self._countdown_timer.stop()
            self.countdown.emit("")
            return
        self.countdown.emit(self.pomodoro_status())

    def start_pomodoro(self) -> bool:
        if self.pomodoro.active:
            return False
        self.pomodoro.start(datetime.now())
        self.pomodoro_changed.emit("专注")
        self._countdown_timer.start()
        self._emit_countdown()
        return True

    def stop_pomodoro(self) -> None:
        if self.pomodoro.active:
            self.pomodoro.stop()
            self.pomodoro_changed.emit("结束")
        self._countdown_timer.stop()
        self.countdown.emit("")

    @property
    def pomodoro_active(self) -> bool:
        return self.pomodoro.active

    def pomodoro_status(self) -> str:
        if not self.pomodoro.active:
            return "未开始"
        label = "专注中" if self.pomodoro.stage is PomodoroStage.FOCUS else "休息中"
        return f"{label} {self.pomodoro.remaining_text(datetime.now())}"
