"""把磨砂材质贴到「菜单」与「设置窗口」上（Qt 侧）。

主窗口**不参与**：桌面宠物窗口必须绝对透明，任何底色都会毁掉不规则透明效果。
这里只服务两块真正的 UI 面板——右键/托盘菜单、设置对话框。

两条路：
1. 系统 Acrylic（``SetWindowCompositionAttribute``）——真模糊，Win10 1803+ 可用；
2. 自绘退化底——alpha 更高的半透明深色 + 细描边，保证任何壁纸下文字都可读。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QWidget

from . import platform_win
from .frosted import (
    ACRYLIC_TINT,
    BORDER,
    DIALOG_RADIUS,
    FALLBACK_TINT,
    MENU_RADIUS,
    FrostedPlan,
    clamp_radius,
    plan_frosted,
)

#: 自绘底的描边颜色。
BORDER_COLOR = QColor(*BORDER)

#: 系统磨砂生效时菜单底色的 alpha（留足够透明度才看得到模糊）。
ACRYLIC_MENU_ALPHA = 150

#: 设置窗口里唯一必须手动清底的部件（其余容器默认不填充背景）。
DIALOG_QSS = """
QTabWidget::pane { background: transparent; border: 1px solid rgba(255, 255, 255, 30);
                   border-radius: 8px; top: -1px; }
QTabBar::tab { background: transparent; padding: 6px 14px; margin: 2px 2px 0 0;
               border-radius: 6px; }
QTabBar::tab:selected { background: rgba(255, 255, 255, 34); }
QTabBar::tab:hover:!selected { background: rgba(255, 255, 255, 18); }
QTabWidget::tab-bar { alignment: left; }

QGroupBox { border: 1px solid rgba(255, 255, 255, 34); border-radius: 8px;
            margin-top: 12px; padding: 10px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
                   left: 10px; padding: 0 4px; color: #b9c4d4; }

QComboBox, QTimeEdit { background: rgba(48, 52, 63, 235);
                       border: 1px solid rgba(255, 255, 255, 44);
                       border-radius: 6px; padding: 3px 8px; color: #e8ecf3;
                       min-height: 20px; }
QComboBox:hover, QTimeEdit:hover { border-color: rgba(120, 170, 255, 190); }
QComboBox QAbstractItemView { background: #23262f; color: #e8ecf3;
                              border: 1px solid rgba(255, 255, 255, 44);
                              selection-background-color: #3d6ea8;
                              selection-color: #ffffff; outline: none; }

QPushButton { background: rgba(56, 60, 72, 236); color: #e8ecf3;
              border: 1px solid rgba(255, 255, 255, 46); border-radius: 6px;
              padding: 4px 14px; }
QPushButton:hover { background: rgba(72, 78, 94, 240); }
QPushButton:pressed { background: rgba(46, 50, 60, 240); }

QSlider::groove:horizontal { height: 4px; background: rgba(255, 255, 255, 44);
                             border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4d8bd8; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -5px 0; border-radius: 6px;
                             background: #dfe7f2; }

QToolButton#dialog_close { color: #dfe7f2; border: none; padding: 2px 6px;
                           border-radius: 4px; }
QToolButton#dialog_close:hover { background: rgba(255, 255, 255, 30); }

QScrollArea { background: transparent; border: none; }
"""


def current_plan(enabled: bool, radius: int = MENU_RADIUS) -> FrostedPlan:
    """按当前桌面能力算出材质计划（菜单与设置各用各的半径）。"""
    compositing, remote = platform_win.display_capabilities()
    return plan_frosted(
        enabled=bool(enabled),
        radius=radius,
        acrylic_available=platform_win.acrylic_available(),
        compositing=compositing,
        remote=remote,
    )


def background_color(plan: FrostedPlan, *, menu: bool = False) -> QColor:
    """面板底色：系统模糊时更透一点，退化时更实一点。"""
    red, green, blue, alpha = ACRYLIC_TINT if plan.acrylic else FALLBACK_TINT
    if menu and plan.acrylic:
        alpha = ACRYLIC_MENU_ALPHA
    return QColor(red, green, blue, alpha)


def menu_stylesheet(plan: FrostedPlan) -> str:
    color = background_color(plan, menu=True)
    radius = clamp_radius(plan.radius)
    return f"""
QMenu {{
    background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});
    border: 1px solid rgba({BORDER[0]}, {BORDER[1]}, {BORDER[2]}, {BORDER[3]});
    border-radius: {radius}px;
    padding: 6px;
    color: #eef1f6;
}}
QMenu::item {{ padding: 6px 24px 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background-color: rgba(255, 255, 255, 40); }}
QMenu::item:disabled {{ color: rgba(238, 241, 246, 108); }}
QMenu::separator {{ height: 1px; background: rgba(255, 255, 255, 34); margin: 5px 10px; }}
QMenu::indicator {{ width: 14px; height: 14px; }}
"""


def dark_palette() -> QPalette:
    """设置窗口的深色调色板：磨砂底上必须配浅色文字，否则读不清。"""
    palette = QPalette()
    window = QColor(28, 31, 39)
    text = QColor(232, 236, 243)
    base = QColor(35, 38, 48)
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(40, 44, 55))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, QColor(44, 48, 59))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 158, 172))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(64, 110, 168))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(122, 130, 145))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(122, 130, 145)
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(122, 130, 145)
    )
    return palette


def paint_background(painter: QPainter, rect: QRectF, plan: FrostedPlan) -> None:
    """画磨砂底：圆角半透明填充 + 一圈细描边。"""
    radius = clamp_radius(plan.radius)
    path = QPainterPath()
    path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    painter.fillPath(path, background_color(plan))
    painter.setPen(QPen(BORDER_COLOR, 1.0))
    painter.drawPath(path)


def apply_native(widget: QWidget, plan: FrostedPlan) -> bool:
    """把系统磨砂贴到已创建 HWND 的窗口上；失败返回 False。"""
    if not plan.enabled or not plan.acrylic:
        return False
    try:
        hwnd = int(widget.winId())
    except Exception:
        return False
    if not platform_win.set_acrylic(hwnd, ACRYLIC_TINT):
        return False
    platform_win.round_corners(hwnd)
    return True


def apply_menu(menu: QWidget, plan: FrostedPlan) -> bool:
    """菜单上材质；返回系统模糊是否真的生效。"""
    if not plan.enabled:
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        menu.setStyleSheet("")
        return False
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menu.setStyleSheet(menu_stylesheet(plan))
    return apply_native(menu, plan)


def prepare_dialog(dialog: QWidget, plan: FrostedPlan) -> bool:
    """设置窗口上材质：无边框 + 透明底 + 深色调色板（+ 系统模糊）。"""
    if not plan.enabled:
        return False
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    dialog.setAutoFillBackground(False)
    dialog.setPalette(dark_palette())
    dialog.setStyleSheet(DIALOG_QSS)
    return apply_native(dialog, plan)


def dialog_plan(enabled: bool) -> FrostedPlan:
    return current_plan(enabled, DIALOG_RADIUS)
