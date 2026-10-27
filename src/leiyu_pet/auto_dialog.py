"""自动移动结束后是否来一段对话的纯逻辑（可单测，不依赖 Qt）。"""

from __future__ import annotations

import random

#: 设置页/托盘里提供的概率档位。
DIALOG_CHANCES = (0, 25, 50, 75, 100)
CHANCE_LABELS = {0: "关闭", 25: "低 25%", 50: "中 50%", 75: "高 75%", 100: "总是 100%"}

#: 自动发起的对话走哪种模式。
DIALOG_MODES = ("crosstalk", "battle", "random")
MODE_LABELS = {"crosstalk": "相声模式", "battle": "决战模式", "random": "随机"}


def clamp_chance(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return min(max(number, 0), 100)


def should_start_dialog(chance: object, roll: float) -> bool:
    """``roll`` 取 ``random.random()``（0.0-1.0）；小于概率则发起。"""
    percent = clamp_chance(chance)
    if percent <= 0:
        return False
    return float(roll) * 100.0 < percent


def resolve_mode(mode: str, rng: random.Random | None = None) -> str:
    """把模式解析成具体实现；random 时在相声/决战之间等概率选。"""
    if mode in ("crosstalk", "battle"):
        return mode
    return (rng or random).choice(("crosstalk", "battle"))
