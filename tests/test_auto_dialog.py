"""自动移动后触发对话的概率逻辑测试。"""

from __future__ import annotations

import random

from leiyu_pet.auto_dialog import (
    DIALOG_CHANCES,
    clamp_chance,
    resolve_mode,
    should_start_dialog,
)


def test_chance_is_clamped_to_percent_range() -> None:
    assert clamp_chance(-5) == 0
    assert clamp_chance(150) == 100
    assert clamp_chance("bad") == 0
    assert clamp_chance(75) == 75


def test_all_presets_are_sane() -> None:
    assert DIALOG_CHANCES[0] == 0
    assert DIALOG_CHANCES[-1] == 100
    assert list(DIALOG_CHANCES) == sorted(DIALOG_CHANCES)


def test_zero_never_starts() -> None:
    for roll in (0.0, 0.5, 0.999):
        assert should_start_dialog(0, roll) is False


def test_hundred_always_starts() -> None:
    for roll in (0.0, 0.5, 0.999):
        assert should_start_dialog(100, roll) is True


def test_threshold_is_strict() -> None:
    assert should_start_dialog(50, 0.499) is True
    assert should_start_dialog(50, 0.5) is False
    assert should_start_dialog(25, 0.25) is False


def test_resolve_mode_passes_explicit_modes() -> None:
    assert resolve_mode("crosstalk") == "crosstalk"


def test_unknown_mode_falls_back_to_crosstalk() -> None:
    assert resolve_mode("nonsense", random.Random(2)) == "crosstalk"
    assert resolve_mode("battle", random.Random(2)) == "crosstalk"
