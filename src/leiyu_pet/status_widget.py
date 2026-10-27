"""独立的状态气泡：番茄钟倒计时等常驻信息专用。

与对话气泡（``CaptionWidget``）分开，互不覆盖——说话的台词走对话气泡，
倒计时走这一条小胶囊，两者可以同时显示。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

#: 状态条高度（窗口底部专门留出这一段）。
STATUS_HEIGHT = 26

BACKGROUND = QColor(24, 26, 32, 205)
FOREGROUND = QColor(255, 255, 255, 235)
PADDING_X = 10
PADDING_Y = 3


class StatusWidget(QWidget):
    """透明的状态胶囊；没有文字时自动隐藏，不占视觉空间。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self._font_size = 9
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()

    def text(self) -> str:
        return self._text

    def font_size(self) -> int:
        return self._font_size

    def set_font_size(self, size: int) -> None:
        self._font_size = min(max(int(size), 8), 16)
        self.update()

    def set_text(self, text: str | None) -> None:
        message = (text or "").strip()
        if message == self._text:
            return
        self._text = message
        if message:
            self.show()
            self.raise_()
        else:
            self.hide()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt 命名
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont(self.font())
        font.setPointSize(self._font_size)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_width = metrics.horizontalAdvance(self._text)
        width = min(self.width() - 4, text_width + PADDING_X * 2)
        height = metrics.height() + PADDING_Y * 2
        rect = QRectF((self.width() - width) / 2.0, 1.0, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(rect, height / 2.0, height / 2.0)
        painter.setPen(FOREGROUND)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)
