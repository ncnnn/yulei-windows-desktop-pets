"""磨砂 UI 层（Qt 侧）测试：自绘背板、图标、菜单与控件样式。

只覆盖「画得像不像、材质有没有真正贴上去」，不涉及桌宠主窗口——主窗口必须
绝对透明，见 ``test_pet_windows.py`` 里的穿透用例。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QMenu, QWidget  # noqa: E402

from leiyu_pet import frosted_ui, paths  # noqa: E402
from leiyu_pet.frosted import DISABLED_PLAN, plan_frosted  # noqa: E402


@pytest.fixture
def painted_plan():
    """自绘退化底（没有系统模糊），测试环境里最稳定的那一路。"""
    return plan_frosted(enabled=True, acrylic_available=False)


@pytest.fixture
def icon_dir(tmp_path, monkeypatch):
    """把图标目录指到临时目录，避免污染真实用户目录与污染其它用例。"""
    monkeypatch.setattr(paths, "base_dir", lambda: tmp_path)
    monkeypatch.setattr(frosted_ui, "_icon_cache", None)
    return tmp_path


def _render(widget: QWidget, size=None) -> QImage:
    size = size or widget.size()
    image = QImage(size, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    widget.render(image)
    return image


def test_icons_are_written_to_disk(qapp, icon_dir) -> None:
    """勾选与 chevron 必须真的落到磁盘——QSS 的 image 只认文件路径。"""
    icons = frosted_ui.icon_paths()
    assert set(icons) == {"check", "chevron_down", "chevron_right"}
    for kind, path in icons.items():
        assert path, f"{kind} 没生成"
        assert Path(path).is_file(), f"{kind} 指向不存在的文件"
        assert Path(path).stat().st_size > 0


def test_icon_paths_are_cached(qapp, icon_dir) -> None:
    first = frosted_ui.icon_paths()
    second = frosted_ui.icon_paths()
    assert first is second


def test_stylesheet_references_every_icon(qapp, icon_dir) -> None:
    menu = frosted_ui.menu_stylesheet(plan_frosted(enabled=True))
    dialog = frosted_ui.dialog_stylesheet()
    assert 'image: url("' in menu
    assert "chevron_right" in menu
    assert "chevron_down" in dialog
    assert "check.png" in dialog
    # 占位符必须全部替换掉，否则 QSS 会当成坏路径而丢样式
    assert "__CHEVRON" not in menu
    assert "__CHECK" not in dialog


def test_stylesheet_falls_back_when_icons_unavailable(qapp, monkeypatch) -> None:
    """写不出图标时不能留空 url，否则整条规则会让 Qt 报警。"""
    monkeypatch.setattr(frosted_ui, "_icon_cache", None)
    monkeypatch.setattr(frosted_ui, "_ui_dir", lambda: None)
    text = frosted_ui.dialog_stylesheet()
    assert "__CHECK__" not in text
    assert 'image: url("")' not in text


def test_disabled_plan_has_no_stylesheet() -> None:
    assert frosted_ui.menu_stylesheet(DISABLED_PLAN) == ""


def test_menu_surface_paints_glass_but_leaves_corners_clear(qapp, painted_plan) -> None:
    image = QImage(260, 220, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    frosted_ui.paint_menu_surface(painter, QRectF(0, 0, 260, 220), painted_plan)
    painter.end()
    center = image.pixelColor(130, 110)
    assert center.alpha() > 200
    assert center.red() < 90  # 深色玻璃，不是白底
    assert image.pixelColor(1, 1).alpha() == 0
    # 顶部比底部亮：渐变方向不能反
    assert image.pixelColor(130, 6).red() >= image.pixelColor(130, 214).red()


def test_panel_paints_soft_shadow_outside_the_glass(qapp, painted_plan) -> None:
    image = QImage(400, 400, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    frosted_ui.paint_panel(painter, QRectF(0, 0, 400, 400), painted_plan, shadow=14)
    painter.end()
    # 面板本体不透明；阴影区半透明；窗口最外圈仍然透
    assert image.pixelColor(200, 200).alpha() > 200
    edge = image.pixelColor(200, 9)
    assert 0 < edge.alpha() < 200
    assert image.pixelColor(200, 0).alpha() < 40


def test_paint_helpers_do_nothing_when_disabled(qapp) -> None:
    image = QImage(120, 120, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    frosted_ui.paint_menu_surface(painter, QRectF(0, 0, 120, 120), DISABLED_PLAN)
    frosted_ui.paint_panel(painter, QRectF(0, 0, 120, 120), DISABLED_PLAN)
    painter.end()
    assert image.pixelColor(60, 60).alpha() == 0


def test_submenu_keeps_the_frosted_class(qapp, icon_dir, painted_plan) -> None:
    parent = frosted_ui.FrostedMenu()
    child = frosted_ui.submenu(parent, "挑一段")
    assert isinstance(child, frosted_ui.FrostedMenu)
    assert child.title() == "挑一段"
    titles = [action.text() for action in parent.actions()]
    assert titles == ["挑一段"]
    parent.deleteLater()


def test_apply_menu_toggles_translucency_and_font(qapp, icon_dir, painted_plan) -> None:
    menu = QMenu()
    assert frosted_ui.apply_menu(menu, painted_plan) is False  # 无 Acrylic，退化
    assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert menu.font().pixelSize() == 13
    assert "border-radius" in menu.styleSheet()

    assert frosted_ui.apply_menu(menu, DISABLED_PLAN) is False
    assert not menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert menu.styleSheet() == ""
    menu.deleteLater()


def test_frosted_menu_sets_plan_and_paints(qapp, icon_dir, painted_plan) -> None:
    menu = frosted_ui.FrostedMenu()
    menu.addAction("测试项")
    menu.set_plan(painted_plan)
    assert menu.plan == painted_plan
    image = _render(menu, menu.sizeHint())
    assert image.pixelColor(image.width() // 2, image.height() // 2).alpha() > 0
    menu.deleteLater()


def test_chevron_style_handles_degenerate_rects(qapp) -> None:
    """箭头绘制不能因为矩形为空就崩（布局未完成时会传空 rect）。"""
    image = QImage(20, 20, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    style = frosted_ui.FrostedStyle()
    style._draw_chevron(painter, QRectF(), down=True)
    style._draw_chevron(painter, QRectF(2, 2, 16, 16), down=False)
    painter.end()
    painted = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert painted > 0
