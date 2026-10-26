"""相声模式：两只桌宠按 1-2-1-2 的节奏交替，把多句连续说完。

这里只做纯逻辑（不导入 PySide6）：给定总句数决定角色序列，并按播放完成
事件逐句推进。真正的播放由 ``PetController`` 执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import PlaybackCommand, Role

MIN_LINES = 2
MAX_LINES = 20
DEFAULT_LINES = 6
#: 菜单里提供的快捷句数，避免用户面对一个无意义的自由输入框。
LINE_PRESETS = (4, 6, 8, 10, 12)


def clamp_lines(lines: int) -> int:
    """把句数夹到合理区间，非法输入回退默认值。"""
    try:
        value = int(lines)
    except (TypeError, ValueError):
        return DEFAULT_LINES
    return min(max(value, MIN_LINES), MAX_LINES)


def crosstalk_roles(lines: int = DEFAULT_LINES, lead: Role = "lei") -> list[Role]:
    """返回交替的角色序列，例如 ``lines=4, lead="lei"`` → lei, yu, lei, yu。"""
    total = clamp_lines(lines)
    other: Role = "yu" if lead == "lei" else "lei"
    return [lead if index % 2 == 0 else other for index in range(total)]


@dataclass(slots=True)
class CrosstalkDirector:
    """按顺序派发多句台词；每句播完才推到下一句。"""

    commands: list[PlaybackCommand] = field(default_factory=list)
    index: int = 0
    running: bool = False

    def start(self, commands: list[PlaybackCommand]) -> PlaybackCommand:
        if not commands:
            raise ValueError("相声模式至少需要一句台词")
        self.commands = list(commands)
        self.index = 0
        self.running = True
        return self.commands[0]

    def finished(self, role: str, clip_id: int) -> PlaybackCommand | None:
        """当前这句播完后返回下一句；序列结束或事件不匹配时返回 None。"""
        if not self.running or self.index >= len(self.commands):
            return None
        current = self.commands[self.index]
        if current.role != role or current.clip_id != clip_id:
            return None
        self.index += 1
        if self.index >= len(self.commands):
            self.cancel()
            return None
        return self.commands[self.index]

    def cancel(self) -> None:
        self.commands = []
        self.index = 0
        self.running = False

    @property
    def remaining(self) -> int:
        if not self.running:
            return 0
        return max(len(self.commands) - self.index, 0)

    @property
    def position(self) -> int:
        """当前是第几句（1 起算），未运行时为 0。"""
        return self.index + 1 if self.running else 0
