"""桌宠字幕气泡：圆角深色底 + 白色文字，由外部逐句 set_caption。"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

BACKGROUND_RGBA = (16, 16, 20, 214)
FOREGROUND_RGBA = (255, 255, 255, 242)
BORDER_RGBA = (255, 255, 255, 48)
BUBBLE_RADIUS = 12.0
PADDING = 10
FONT_SIZE = 11
MAX_BUBBLE_HEIGHT = 96

TEXT_FLAGS = Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop


class CaptionWidget(QWidget):
    """透明背景的字幕气泡，鼠标事件直接穿透给父窗口。"""

    def __init__(self, parent: QWidget | None = None, *, font_size: int = FONT_SIZE) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._caption = ""
        self._font_size = int(font_size)

    def set_caption(self, text: str | None) -> None:
        value = (text or "").strip()
        if value == self._caption:
            return
        self._caption = value
        self.update()
        self.updateGeometry()

    def caption(self) -> str:
        return self._caption

    def clear(self) -> None:
        self.set_caption("")

    @property
    def is_empty(self) -> bool:
        return not self._caption

    def font_size(self) -> int:
        return self._font_size

    def set_font_size(self, value: int) -> None:
        self._font_size = int(value)
        self.update()

    def bubble_rect(self) -> QRect:
        """当前文本对应的气泡矩形（控件局部坐标，水平居中）。"""
        if not self._caption:
            return QRect()
        metrics = QFontMetrics(self._font())
        available = max(1, self.width() - 2 * PADDING)
        text_rect = metrics.boundingRect(
            QRect(0, 0, available, MAX_BUBBLE_HEIGHT), TEXT_FLAGS, self._caption
        )
        width = min(text_rect.width() + 2 * PADDING, self.width())
        height = min(text_rect.height() + 2 * PADDING, self.height() or MAX_BUBBLE_HEIGHT)
        left = max(0, (self.width() - width) // 2)
        return QRect(left, 0, width, height)

    def sizeHint(self) -> QSize:
        rect = self.bubble_rect()
        return rect.size() if rect.isValid() else super().sizeHint()

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSize(self._font_size)
        return font

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._caption:
            return
        bubble = self.bubble_rect()
        if not bubble.isValid():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(bubble), BUBBLE_RADIUS, BUBBLE_RADIUS)
        painter.fillPath(path, QColor(*BACKGROUND_RGBA))
        painter.setPen(QColor(*BORDER_RGBA))
        painter.drawPath(path)
        painter.setPen(QColor(*FOREGROUND_RGBA))
        painter.setFont(self._font())
        inner = bubble.adjusted(PADDING, PADDING, -PADDING, -PADDING)
        painter.drawText(inner, TEXT_FLAGS, self._caption)
