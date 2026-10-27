"""窗口几何与坐标迁移的纯逻辑测试。"""

from __future__ import annotations

from leiyu_pet.layout import (
    BOTTOM_EXTRA,
    PAD_X,
    TOP,
    head_box,
    legacy_window_height,
    migrate_top_left,
    to_top_left,
    window_height,
    window_width,
)


def test_window_width_keeps_head_padding() -> None:
    assert window_width(220) == 220 + 2 * PAD_X


def test_head_box_matches_legacy_position() -> None:
    box = head_box(220)
    assert (box.x, box.y, box.width, box.height) == (PAD_X, TOP, 220.0, 220.0)
    assert box.bottom == TOP + 220
    assert box.center_x == PAD_X + 110


def test_window_height_adds_caption_area() -> None:
    assert window_height(400) == 400 + BOTTOM_EXTRA


def test_legacy_migration_uses_old_window_height() -> None:
    assert legacy_window_height(220) == 220 + TOP + BOTTOM_EXTRA
    width = 220 + 2 * PAD_X
    assert migrate_top_left(100, 200, 220) == [
        100 + width // 2,
        200 + legacy_window_height(220),
    ]


def test_bottom_center_round_trip() -> None:
    x, y = to_top_left(500, 900, 316, 529)
    assert (x, y) == (500 - 158, 900 - 529)


def test_migration_keeps_feet_on_the_same_pixel() -> None:
    """旧坐标的底边 = y + 旧高度，迁移后按底边还原必须落在同一行。"""
    pet_size = 220
    old_x, old_y = 960, 380
    center_x, center_y = migrate_top_left(old_x, old_y, pet_size)
    # 新版窗口更高，但底边中点不变
    new_x, new_y = to_top_left(center_x, center_y, 316, 529)
    assert new_y + 529 == old_y + legacy_window_height(pet_size)
    assert new_x + 158 == old_x + (pet_size + 2 * PAD_X) // 2
