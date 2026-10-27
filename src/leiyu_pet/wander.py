"""自动游走：在可用屏幕区域内为桌宠挑一个随机落点。

纯几何 + 注入随机源，便于测试；真正的移动由运行时用定时器逐步完成。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

#: 两次落点之间至少挪动这么多像素，避免原地小碎步看起来像抽搐。
MIN_TRAVEL = 120


@dataclass(frozen=True, slots=True)
class PlayArea:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def clamp_position(x: int, y: int, width: int, height: int, area: PlayArea) -> tuple[int, int]:
    """把窗口左上角夹进区域，保证窗口整体可见。"""
    max_x = area.left + max(0, area.width - width)
    max_y = area.top + max(0, area.height - height)
    return (
        min(max(int(x), area.left), max_x),
        min(max(int(y), area.top), max_y),
    )


def next_target(
    current: tuple[int, int],
    width: int,
    height: int,
    area: PlayArea,
    *,
    rng: random.Random | None = None,
    min_travel: int = MIN_TRAVEL,
    attempts: int = 8,
) -> tuple[int, int]:
    """在当前屏幕内挑一个离当前位置足够远的随机落点。"""
    generator = rng or random
    start_x, start_y = clamp_position(current[0], current[1], width, height, area)
    candidate = (start_x, start_y)
    span_x = max(0, area.width - width)
    span_y = max(0, area.height - height)
    for _ in range(max(1, attempts)):
        x = area.left + generator.randint(0, span_x)
        y = area.top + generator.randint(0, span_y)
        candidate = (x, y)
        if abs(x - start_x) + abs(y - start_y) >= min_travel:
            return candidate
    return candidate
