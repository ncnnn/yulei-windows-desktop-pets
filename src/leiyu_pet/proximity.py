"""靠近判定、迟滞与歪头方向。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2


def gap(a: Rect, b: Rect) -> float:
    horizontal = max(0.0, a.left - b.right, b.left - a.right)
    vertical = max(0.0, a.top - b.bottom, b.top - a.bottom)
    return math.hypot(horizontal, vertical)


def angle_for_delta(dx: float, *, radians: float = 0.20) -> float:
    """沿用 macOS 原版：目标在右侧时为负角，左侧时为正角。"""
    return -radians if dx >= 0 else radians


@dataclass(slots=True)
class ProximityTracker:
    distance: float = 32.0
    hysteresis: float = 24.0
    near: bool = False

    def update(self, a: Rect, b: Rect) -> bool:
        current_gap = gap(a, b)
        if self.near:
            if current_gap > self.distance + self.hysteresis:
                self.near = False
        elif current_gap <= self.distance:
            self.near = True
        return self.near

    def tilt_angles(self, lei: Rect, yu: Rect, *, enabled: bool = True) -> tuple[float, float]:
        if not enabled or not self.near:
            return 0.0, 0.0
        return (
            angle_for_delta(yu.center_x - lei.center_x),
            angle_for_delta(lei.center_x - yu.center_x),
        )
