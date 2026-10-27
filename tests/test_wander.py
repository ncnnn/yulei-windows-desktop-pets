"""自动游走几何逻辑测试。"""

from __future__ import annotations

import random

from leiyu_pet.wander import PlayArea, clamp_position, next_target

AREA = PlayArea(0, 0, 1000, 700)


def test_clamp_keeps_window_inside() -> None:
    assert clamp_position(-50, -50, 200, 300, AREA) == (0, 0)
    assert clamp_position(5000, 5000, 200, 300, AREA) == (800, 400)
    assert clamp_position(100, 120, 200, 300, AREA) == (100, 120)


def test_clamp_handles_window_larger_than_area() -> None:
    tiny = PlayArea(10, 20, 100, 100)
    assert clamp_position(0, 0, 500, 500, tiny) == (10, 20)


def test_next_target_stays_inside_and_moves_far_enough() -> None:
    rng = random.Random(1234)
    target = next_target((0, 0), 200, 300, AREA, rng=rng)
    assert 0 <= target[0] <= 800
    assert 0 <= target[1] <= 400
    assert abs(target[0]) + abs(target[1]) >= 120


def test_next_target_returns_inside_even_without_room() -> None:
    tiny = PlayArea(0, 0, 100, 100)
    assert next_target((0, 0), 200, 200, tiny) == (0, 0)
