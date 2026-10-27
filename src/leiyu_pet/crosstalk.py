"""相声模式：两只桌宠按 1-2-1-2 的节奏交替，把多句连续说完。

这里只做纯逻辑（不导入 PySide6）：给定总句数决定角色序列，并按播放完成
事件逐句推进。真正的播放由 ``PetController`` 执行。
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from .models import DialoguePair, PlaybackCommand, Role

MIN_LINES = 2
MAX_LINES = 20
DEFAULT_LINES = 6
#: 菜单里提供的快捷句数，避免用户面对一个无意义的自由输入框。
LINE_PRESETS = (4, 6, 8, 10, 12)

#: 决战模式的逐句音量：第一句 20%，最后一句 70%，中间线性递增。
BATTLE_START_VOLUME = 0.20
BATTLE_END_VOLUME = 0.70


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


def commands_from_pairs(
    pairs: Sequence[DialoguePair],
    lines: int = DEFAULT_LINES,
    *,
    rng: random.Random | None = None,
) -> list[PlaybackCommand]:
    """按「一问一答」生成严格交替的命令序列。

    与旧实现的关键区别：这里不再给每只角色各抽一句，而是整组取用
    ``pairs.json`` 里的问答对——雷军问哪句，余承东就答对应的那句。

    顺序规则：第一轮按素材里的原始顺序走完，**用完之后整轮打乱再循环**，
    而不是每句各自随机重选（那样会出现答非所问）。
    """
    total = clamp_lines(lines)
    if not pairs:
        raise ValueError("素材包没有可用的问答组")
    source = list(pairs)
    commands: list[PlaybackCommand] = []
    order = list(source)
    index = 0
    while len(commands) < total:
        if index >= len(order):
            # 上一轮走完：整轮重排，保持每组问答仍是成对出现的。
            order = list(source)
            if len(order) > 1:
                (rng or random).shuffle(order)
            index = 0
        pair = order[index]
        index += 1
        commands.append(PlaybackCommand("lei", pair.lei))
        if len(commands) < total:
            commands.append(PlaybackCommand("yu", pair.yu))
    return commands


def battle_multipliers(count: int) -> list[float]:
    """决战模式每句的阶梯目标音量：0.20 线性升到 0.70。

    名字沿用「multiplier」，但返回的是**绝对目标音量**（0.20-0.70）；
    实际播放音量由 ``PetController`` 取 ``min(目标值, 用户当前音量)``。
    """
    total = max(1, int(count))
    if total == 1:
        return [BATTLE_END_VOLUME]
    step = (BATTLE_END_VOLUME - BATTLE_START_VOLUME) / (total - 1)
    return [round(BATTLE_START_VOLUME + step * index, 3) for index in range(total)]


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
