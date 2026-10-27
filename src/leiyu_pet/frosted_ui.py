"""把磨砂材质贴到「菜单」与「设置窗口」上（Qt 侧）。

主窗口**不参与**：桌面宠物窗口必须绝对透明，任何底色都会毁掉不规则透明效果。
这里只服务两块真正的 UI 面板——右键/托盘菜单、设置对话框。

三条路各司其职：

1. ``paint_menu_surface`` / ``paint_panel``：自绘玻璃面（垂直渐变 + 顶部内高光 +
   底部内阴影 + 1px 描边）。比纯 QSS 单色块有厚度，也不会像系统 Acrylic 那样
   把圆角切掉。
2. ``SetWindowCompositionAttribute``（``platform_win.set_acrylic``）：真模糊，
   Win10 1803+ 可用。它只负责「透」，不负责「形」，所以和自绘面能叠在一起用。
3. ``FrostedMenu`` / ``FrostedStyle``：把 Qt 默认那种老式控件外观换掉——菜单
   自己画玻璃背板，下拉框的实心三角箭头改成圆润 chevron。

设计 token 集中在文件顶部，改配色只动这一处。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import QMenu, QProxyStyle, QStyle, QWidget

from . import platform_win
from .frosted import (
    ACRYLIC_TINT,
    DIALOG_RADIUS,
    MENU_RADIUS,
    FrostedPlan,
    plan_frosted,
)

# ---------------------------------------------------------------- 设计 token

#: 正文文字色 / 次要文字色 / 高亮强调色。
TEXT = QColor(232, 237, 245)
TEXT_DIM = QColor(154, 164, 182)
ACCENT = QColor(88, 148, 255)
#: 面板描边：比纯白更柔，浅色壁纸上也不会显得脏。
BORDER_COLOR = QColor(255, 255, 255, 44)
#: 顶部那道 1px 内高光：玻璃受光的关键，没有它面板会像一张贴纸。
TOP_GLOW = QColor(255, 255, 255, 56)

#: 菜单面：上浅下深，模拟光从上方打下来。
MENU_TINT_TOP = QColor(46, 50, 62, 232)
MENU_TINT_BOTTOM = QColor(30, 33, 42, 240)
#: Acrylic 生效时底色要更透，否则看不见背后的模糊。
MENU_ACRYLIC_TOP = QColor(38, 42, 54, 168)
MENU_ACRYLIC_BOTTOM = QColor(24, 27, 35, 182)

#: 设置面板：比菜单略亮，面积大、太暗会压抑。
PANEL_TINT_TOP = QColor(42, 46, 58, 238)
PANEL_TINT_BOTTOM = QColor(27, 30, 38, 244)
PANEL_ACRYLIC_TOP = QColor(34, 38, 48, 190)
PANEL_ACRYLIC_BOTTOM = QColor(22, 25, 32, 205)

#: 圆角统一走一套刻度，避免「外面 14、里面 6」的拼贴感。
RADIUS_MENU = 12
RADIUS_PANEL = 16
RADIUS_ITEM = 8
RADIUS_FIELD = 8


def menu_font() -> QFont:
    """菜单字体：13px 才撑得住上下 7px 的内边距，不会挤成一片。"""
    font = QFont()
    font.setPixelSize(13)
    return font


def dialog_font() -> QFont:
    font = QFont()
    font.setPixelSize(13)
    return font


# ---------------------------------------------------------------- 样式表

MENU_QSS = """
QMenu {
    background: transparent;
    border: none;
    padding: 6px;
    color: #e8edf5;
    font-size: 13px;
    min-width: 210px;
}
QMenu::item {
    /* min-width 必须给：只写 padding 时 QStyle 只按文字宽度算 item 矩形，
       菜单却被 QMenu 的 min-width 撑宽，右侧会留出一条「看得见、点不到」的死区
       （实测 222px 宽的菜单里 item 只有 114px）。 */
    min-width: 180px;
    padding: 6px 26px 6px 10px;
    border-radius: 8px;
}
QMenu::item:selected {
    background: rgba(88, 148, 255, 46);
    color: #ffffff;
}
QMenu::item:disabled {
    color: rgba(232, 237, 245, 104);
}
QMenu::separator {
    height: 1px;
    background: rgba(255, 255, 255, 26);
    margin: 6px 12px;
}
QMenu::indicator {
    width: 14px;
    height: 14px;
    margin-left: 4px;
}
QMenu::right-arrow {
    image: url("__CHEVRON_RIGHT__");
    width: 11px;
    height: 11px;
    margin-right: 6px;
}
"""

DIALOG_QSS = """
QLabel { color: #d7deea; background: transparent; }
QLabel#dialog_title {
    color: #f4f7fb;
    font-size: 17px;
    font-weight: 600;
}
QLabel#dialog_subtitle { color: #8f9aad; font-size: 11px; }
QLabel#section_hint { color: #97a2b4; font-size: 11px; }

QWidget#dialog_header { background: transparent; }
QFrame#dialog_rule { background: rgba(255, 255, 255, 26); border: none; }

QTabWidget::pane {
    background: transparent;
    border: none;
    margin-top: 4px;
}
QTabWidget::tab-bar { alignment: left; left: 2px; }
QTabBar::tab {
    background: transparent;
    color: #9aa5b7;
    padding: 6px 15px;
    margin: 0 4px 0 0;
    border-radius: 8px;
    font-size: 12px;
}
QTabBar::tab:hover:!selected { background: rgba(255, 255, 255, 16); color: #cfd7e4; }
QTabBar::tab:selected {
    background: rgba(255, 255, 255, 30);
    color: #ffffff;
    font-weight: 600;
}

QGroupBox {
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 12px;
    margin-top: 12px;
    padding: 18px 14px 12px 14px;
    background: rgba(255, 255, 255, 10);
    font-size: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: #c6d0de;
    font-size: 12px;
    font-weight: 600;
}

QComboBox, QTimeEdit, QSpinBox {
    background: rgba(255, 255, 255, 18);
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 8px;
    padding: 4px 10px;
    color: #e6ebf3;
    min-height: 22px;
    font-size: 12px;
}
QComboBox:hover, QTimeEdit:hover { border-color: rgba(88, 148, 255, 150); }
QComboBox:focus, QTimeEdit:focus { border-color: rgba(88, 148, 255, 210); }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border: none;
    background: transparent;
}
/* QTimeEdit 自带上下箭头，在深色圆角框里会露出一块浅灰底，直接藏掉。 */
QTimeEdit::up-button, QTimeEdit::down-button { width: 0; border: none; background: transparent; }
QComboBox::down-arrow {
    image: url("__CHEVRON_DOWN__");
    width: 11px;
    height: 11px;
}
QComboBox QAbstractItemView {
    background: #22252e;
    color: #e6ebf3;
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 8px;
    padding: 4px;
    selection-background-color: rgba(88, 148, 255, 90);
    selection-color: #ffffff;
    outline: none;
}

QCheckBox { color: #d7deea; spacing: 8px; font-size: 12px; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid rgba(255, 255, 255, 62);
    background: rgba(18, 21, 28, 150);
}
QCheckBox::indicator:hover { border-color: rgba(88, 148, 255, 190); }
QCheckBox::indicator:checked {
    background: #4d86e0;
    border-color: #6fa0f0;
    image: url("__CHECK__");
}

QPushButton {
    background: rgba(255, 255, 255, 20);
    color: #e6ebf3;
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 8px;
    padding: 5px 18px;
    font-size: 12px;
    min-height: 20px;
}
QPushButton:hover { background: rgba(255, 255, 255, 34); }
QPushButton:pressed { background: rgba(255, 255, 255, 16); }
QPushButton#inline_action { padding: 5px 16px; }

QSlider::groove:horizontal {
    height: 4px;
    background: rgba(255, 255, 255, 34);
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #4d86e0; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 13px;
    margin: -5px 0;
    border-radius: 7px;
    background: #eef2f8;
    border: 1px solid rgba(0, 0, 0, 60);
}
QSlider::handle:horizontal:hover { background: #ffffff; }

QToolButton#dialog_close {
    color: #aab4c4;
    border: none;
    background: transparent;
    font-size: 15px;
    border-radius: 7px;
}
QToolButton#dialog_close:hover { background: #c4392f; color: #ffffff; }

QScrollArea { background: transparent; border: none; }
QWidget#tab_page { background: transparent; }
QWidget#scroll_viewport { background: transparent; }
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 46);
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


# ---------------------------------------------------------------- 材质计划


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


def dialog_plan(enabled: bool) -> FrostedPlan:
    return current_plan(enabled, DIALOG_RADIUS)


def _tints(plan: FrostedPlan, *, menu: bool) -> tuple[QColor, QColor]:
    if menu:
        return (
            (MENU_ACRYLIC_TOP, MENU_ACRYLIC_BOTTOM)
            if plan.acrylic
            else (MENU_TINT_TOP, MENU_TINT_BOTTOM)
        )
    return (
        (PANEL_ACRYLIC_TOP, PANEL_ACRYLIC_BOTTOM)
        if plan.acrylic
        else (PANEL_TINT_TOP, PANEL_TINT_BOTTOM)
    )


def _fill_glass(
    painter: QPainter, rect: QRectF, radius: float, top: QColor, bottom: QColor
) -> QPainterPath:
    """铺玻璃面：垂直渐变 + 顶部内高光 + 底部内阴影，最后描一圈细边。"""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(0.45, top.darker(106))
    gradient.setColorAt(1.0, bottom)
    painter.fillPath(path, gradient)

    painter.save()
    painter.setClipPath(path)
    # 顶部高光：一条 1px 亮线 + 向下 42% 高度的极淡光晕。
    glow_height = max(rect.height() * 0.42, 2.0)
    glow = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + glow_height))
    glow.setColorAt(0.0, QColor(255, 255, 255, 26))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), glow_height), glow)

    line = QLinearGradient(rect.topLeft(), rect.topRight())
    line.setColorAt(0.0, QColor(255, 255, 255, 0))
    line.setColorAt(0.18, TOP_GLOW)
    line.setColorAt(0.82, TOP_GLOW)
    line.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(
        QRectF(rect.left() + radius, rect.top(), max(rect.width() - 2 * radius, 0.0), 1.0), line
    )

    # 底部内阴影：让面板「压」在壁纸上，有厚度感。
    depth = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    depth.setColorAt(0.0, QColor(0, 0, 0, 0))
    depth.setColorAt(0.62, QColor(0, 0, 0, 0))
    depth.setColorAt(1.0, QColor(0, 0, 0, 74))
    painter.fillRect(rect, depth)
    painter.restore()

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(BORDER_COLOR, 1.0))
    painter.drawPath(path)
    return path


def paint_menu_surface(painter: QPainter, rect: QRectF, plan: FrostedPlan) -> None:
    """菜单背板：圆角玻璃面 + 一圈很淡的外阴影（在 padding 留白里画）。"""
    if not plan.enabled:
        return
    radius = float(max(plan.radius, RADIUS_MENU))
    inner = rect.adjusted(1.0, 1.0, -1.0, -1.0)
    shadow = QPainterPath()
    shadow.addRoundedRect(inner.adjusted(-1.0, 0.5, 1.0, 2.0), radius + 1, radius + 1)
    painter.fillPath(shadow, QColor(0, 0, 0, 46))
    top, bottom = _tints(plan, menu=True)
    _fill_glass(painter, inner, radius, top, bottom)


def paint_panel(painter: QPainter, rect: QRectF, plan: FrostedPlan, shadow: int = 16) -> None:
    """设置面板：多层柔化外阴影 + 玻璃面。

    阴影必须画在窗口内部（``WA_TranslucentBackground`` 窗口没有系统投影），
    所以调用方的布局要留出 ``shadow`` 像素的边距。

    每一圈只画「环」（外矩形减去内矩形），不是一个比一个小的实心矩形——后者
    会层层叠加，靠近面板的那一圈黑得发亮，看起来像一圈硬描边。
    """
    if not plan.enabled:
        return
    radius = float(max(plan.radius, RADIUS_PANEL))
    inner = rect.adjusted(shadow, shadow, -shadow, -shadow)
    steps = 10
    for index in range(1, steps + 1):
        t = index / steps
        alpha = int(52 * (1.0 - t) ** 2.2) + 2
        outer = _shadow_rect(inner, radius, index / steps * shadow)
        hole = _shadow_rect(inner, radius, (index - 1) / steps * shadow)
        painter.fillPath(outer.subtracted(hole), QColor(0, 0, 0, alpha))
    top, bottom = _tints(plan, menu=False)
    _fill_glass(painter, inner.adjusted(0.5, 0.5, -0.5, -0.5), radius, top, bottom)


def _shadow_rect(inner: QRectF, radius: float, spread: float) -> QPainterPath:
    """阴影扩散层：左右等比外扩，下方多扩一点（光从上方来）。"""
    path = QPainterPath()
    path.addRoundedRect(
        inner.adjusted(-spread, -spread * 0.5, spread, spread * 1.4),
        radius + spread,
        radius + spread,
    )
    return path


# ---------------------------------------------------------------- 小图标

#: 图标画在 36px 画布上再缩小，缩到 10~16px 也不会有锯齿。
_ICON_PX = 36
_icon_cache: dict[str, str] | None = None


def _ui_dir():
    """图标落地目录；拿不到可写目录时返回 None（退化为无图标）。"""
    try:
        from . import paths

        folder = paths.base_dir() / "ui"
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    except Exception:
        return None


def _paint_icon(painter: QPainter, *, kind: str) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(255, 255, 255) if kind == "check" else QColor(203, 213, 228))
    # 36px 画布缩到 10~16px 时线宽会按比例变细，所以源图必须画粗一点，
    # 否则缩完只剩一层半透明灰，看起来像没画。
    pen.setWidthF(4.6 if kind == "check" else 5.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    half = _ICON_PX / 2.0
    if kind == "check":
        points = [QPointF(9, half), QPointF(half - 2, _ICON_PX - 11), QPointF(_ICON_PX - 8, 11)]
    elif kind == "chevron_right":
        points = [QPointF(13, 9), QPointF(_ICON_PX - 12, half), QPointF(13, _ICON_PX - 9)]
    else:
        points = [QPointF(9, 13), QPointF(half, _ICON_PX - 12), QPointF(_ICON_PX - 9, 13)]
    painter.drawPolyline(points)


def _icon_image(kind: str) -> QImage:
    image = QImage(_ICON_PX, _ICON_PX, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    _paint_icon(painter, kind=kind)
    painter.end()
    return image


def icon_paths() -> dict[str, str]:
    """确保三个小图标已写到磁盘，返回 QSS 能引用的路径。

    QSS 的 ``image: url(...)`` 只认文件路径（不支持内嵌 data URI），所以勾选
    标记与 chevron 箭头都得先渲染成 PNG。写不出来就返回空串，样式表退化。
    """
    global _icon_cache
    if _icon_cache is not None:
        return _icon_cache
    result = {"check": "", "chevron_down": "", "chevron_right": ""}
    folder = _ui_dir()
    if folder is not None:
        for kind in tuple(result):
            file = folder / f"{kind}.png"
            try:
                if not file.exists():
                    _icon_image(kind).save(str(file), "PNG")
                result[kind] = file.as_posix()
            except Exception:
                result[kind] = ""
    _icon_cache = result
    return result


def _with_icons(template: str, kinds: tuple[str, ...]) -> str:
    """把模板里的 ``__NAME__`` 占位替换成真实路径；缺图则整行删掉。"""
    icons = icon_paths()
    text = template
    for kind in kinds:
        token = f"__{kind.upper()}__"
        if icons.get(kind):
            text = text.replace(token, icons[kind])
        else:
            text = text.replace(f'image: url("{token}");', "")
    return text


# ---------------------------------------------------------------- 控件样式


def menu_stylesheet(plan: FrostedPlan) -> str:
    """菜单样式：开启时背板由 ``FrostedMenu`` 自绘，所以 QSS 背景保持透明。"""
    if not plan.enabled:
        return ""
    return _with_icons(MENU_QSS, ("chevron_right",))


def dialog_stylesheet() -> str:
    return _with_icons(DIALOG_QSS, ("check", "chevron_down"))


def dark_palette() -> QPalette:
    """设置窗口的深色调色板：磨砂底上必须配浅色文字，否则读不清。"""
    palette = QPalette()
    window = QColor(30, 33, 41)
    text = TEXT
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
    palette.setColor(QPalette.ColorRole.Highlight, QColor(77, 134, 224))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(122, 130, 145))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(122, 130, 145)
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(122, 130, 145)
    )
    return palette


def apply_native(widget: QWidget, plan: FrostedPlan) -> bool:
    """把系统模糊贴到已创建 HWND 的窗口上；失败返回 False。"""
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


def prepare_dialog(dialog: QWidget, plan: FrostedPlan) -> bool:
    """设置窗口上材质：无边框 + 透明底 + 深色调色板（+ 系统模糊）。"""
    if not plan.enabled:
        return False
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    dialog.setAutoFillBackground(False)
    dialog.setPalette(dark_palette())
    dialog.setFont(dialog_font())
    dialog.setStyleSheet(dialog_stylesheet())
    return apply_native(dialog, plan)


# ---------------------------------------------------------------- 自绘控件


class FrostedMenu(QMenu):
    """自绘玻璃背板的菜单。

    QSS 只能画单色块，既没有渐变也没有顶部高光，深色壁纸上会显得平。这里在
    ``super().paintEvent`` 之前把背板画好（QSS 背景设为 transparent，不会盖掉），
    文字与悬停高亮仍交给 Qt 处理，不重写项布局。
    """

    def __init__(self, parent: QWidget | None = None, plan: FrostedPlan | None = None) -> None:
        super().__init__(parent)
        self._plan = plan if plan is not None else current_plan(True, MENU_RADIUS)
        self.setFont(menu_font())

    def set_plan(self, plan: FrostedPlan) -> None:
        self._plan = plan
        self.setFont(menu_font())

    @property
    def plan(self) -> FrostedPlan:
        return self._plan

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._plan.enabled:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            paint_menu_surface(painter, QRectF(self.rect()), self._plan)
            painter.end()
        super().paintEvent(event)


class FrostedStyle(QProxyStyle):
    """把下拉框的老式三角箭头换成圆润 chevron。

    Qt 默认用 ``PE_IndicatorArrowDown`` 画实心三角，在深色圆角输入框里很扎眼。
    这里只拦截这一个 primitive，其余全部交回底层 style。
    """

    def __init__(self) -> None:
        # 必须留空：QProxyStyle 会接管传入样式的所有权，传 QApplication.style()
        # 就等于把全局样式交给代理，代理一销毁全局样式也跟着没了——之后任何
        # 控件创建都会 access violation。留空则始终跟随当前应用样式。
        super().__init__()

    def drawPrimitive(  # noqa: N802 - Qt 命名
        self, element, option, painter, widget=None
    ) -> None:
        if element == QStyle.PrimitiveElement.PE_IndicatorArrowDown:
            self._draw_chevron(painter, option.rect, down=True)
            return
        if element == QStyle.PrimitiveElement.PE_IndicatorArrowUp:
            self._draw_chevron(painter, option.rect, down=False)
            return
        super().drawPrimitive(element, option, painter, widget)

    @staticmethod
    def _draw_chevron(painter: QPainter, rect, *, down: bool) -> None:
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(TEXT_DIM, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = rect.center()
        cx = center.x() + 0.5
        cy = center.y() + (0.5 if down else -0.5)
        half_w, half_h = 4.0, 2.1
        sign = 1.0 if down else -1.0
        painter.drawPolyline(
            [
                QPointF(cx - half_w, cy - half_h * sign),
                QPointF(cx, cy + half_h * sign),
                QPointF(cx + half_w, cy - half_h * sign),
            ]
        )
        painter.restore()


def install_style(widget: QWidget) -> FrostedStyle:
    """给窗口装上 chevron 样式，并保证代理对象不被回收。"""
    style = FrostedStyle()
    widget.setStyle(style)
    widget._frosted_style = style  # type: ignore[attr-defined]
    return style


def submenu(parent: QMenu, title: str) -> FrostedMenu:
    """在父菜单下挂一个同样材质的子菜单。

    ``QMenu.addMenu(str)`` 只会造出普通 QMenu，子菜单弹出时没有玻璃背板；
    统一走这个入口，父子都能自绘。
    """
    menu = FrostedMenu(parent)
    menu.setTitle(title)
    parent.addMenu(menu)
    return menu


def apply_menu(menu: QMenu, plan: FrostedPlan) -> bool:
    """菜单上材质；返回系统模糊是否真的生效。"""
    if not plan.enabled:
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        menu.setStyleSheet("")
        return False
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menu.setFont(menu_font())
    menu.setPalette(dark_palette())
    menu.setStyleSheet(menu_stylesheet(plan))
    if isinstance(menu, FrostedMenu):
        menu.set_plan(plan)
    return apply_native(menu, plan)
