"""窗口几何的纯计算：不导入 Qt，方便单测。

窗口由三部分垂直堆叠：头部盒子、火柴人躯体、字幕气泡。窗口本身**不画任何底**，
除了大头像素与火柴人线条之外全部透明（命中测试也按这个口径判定）。头部盒子的大小
与位置始终等于旧版（``pet_size`` 见方），所以「加躯体」只是把窗口向下
加高，头像像素一个都不缩。

坐标约定：
- 旧版位置记录的是**窗口左上角**；
- 新版记录**底边中点**，这样开关躯体/改大小时脚不会沉进屏幕。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 头部盒子左右内边距与顶部留白（沿用旧版数值，保证头像位置不变）。
PAD_X = 48
TOP = 16
#: 头部下方留给字幕气泡的高度。
BOTTOM_EXTRA = 112


@dataclass(frozen=True, slots=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.right and self.y <= y <= self.bottom


def window_width(pet_size: int) -> int:
    return int(pet_size) + 2 * PAD_X


def head_box(pet_size: int) -> Box:
    """头部绘制盒子（窗口局部坐标）。"""
    size = float(pet_size)
    return Box(float(PAD_X), float(TOP), size, size)


def legacy_window_height(pet_size: int) -> int:
    """没有躯体时的窗口高度，用于迁移旧坐标。"""
    return int(pet_size) + TOP + BOTTOM_EXTRA


def window_height(content_bottom: float) -> int:
    """内容底边（头部盒子底或脚底，取较大者）加字幕区。"""
    return int(round(content_bottom)) + BOTTOM_EXTRA


def migrate_top_left(x: int, y: int, pet_size: int) -> list[int]:
    """把旧版「窗口左上角」换算成新版「底边中点」。"""
    width = window_width(pet_size)
    height = legacy_window_height(pet_size)
    return [int(x) + width // 2, int(y) + height]


def to_top_left(center_x: int, center_y: int, width: int, height: int) -> tuple[int, int]:
    """底边中点 → 窗口左上角。"""
    return int(center_x) - int(width) // 2, int(center_y) - int(height)


def is_legacy_position(value: object) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2
