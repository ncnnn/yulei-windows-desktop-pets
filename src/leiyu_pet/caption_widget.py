"""桌宠字幕气泡：圆角深色底 + 白色文字。

表现层细节：
* 打字机效果：文字按 ~24ms 一个字符逐步显示，长句不会一次性糊满；
* 语气符号：句末的 ！？… 会改变气泡描边颜色，让语气可读；
* 说话脉冲：外部把 0..1 的脉冲传进来，气泡轻微缩放，像被声音推着。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

BACKGROUND_RGBA = (16, 16, 20, 214)
FOREGROUND_RGBA = (255, 255, 255, 242)
BORDER_RGBA = (255, 255, 255, 48)
BUBBLE_RADIUS = 12.0
PADDING = 10
FONT_SIZE = 11
MAX_BUBBLE_HEIGHT = 96

#: 打字机节奏与气泡随声音缩放的幅度。
TYPE_INTERVAL_MS = 24
PULSE_SCALE = 0.06

EMOTION_BORDERS = {
    "calm": (255, 255, 255, 48),
    "exclaim": (255, 138, 128, 150),
    "question": (128, 190, 255, 150),
    "ellipsis": (200, 200, 200, 90),
}

TEXT_FLAGS = Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop


def emotion_of(text: str) -> str:
    """按句末标点判断语气，用于气泡描边配色。"""
    stripped = (text or "").strip()
    if not stripped:
        return "calm"
    tail = stripped[-1]
    if tail in "！!":
        return "exclaim"
    if tail in "？?":
        return "question"
    if stripped.endswith("…") or stripped.endswith("..."):
        return "ellipsis"
    return "calm"


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
        self._revealed = 0
        self._pulse = 0.0
        self._typewriter = QTimer(self)
        self._typewriter.setInterval(TYPE_INTERVAL_MS)
        self._typewriter.timeout.connect(self._reveal_next)

    def set_caption(self, text: str | None) -> None:
        value = (text or "").strip()
        if value == self._caption:
            return
        self._caption = value
        self._typewriter.stop()
        self._revealed = 0
        if value:
            self._typewriter.start()
        self.update()
        self.updateGeometry()

    def _reveal_next(self) -> None:
        if self._revealed >= len(self._caption):
            self._typewriter.stop()
            return
        self._revealed += 1
        self.update()
        if self._revealed >= len(self._caption):
            self._typewriter.stop()

    def reveal_all(self) -> None:
        """立即显示完整文字（停止播放时用，避免残留半句）。"""
        self._typewriter.stop()
        self._revealed = len(self._caption)
        self.update()

    def set_pulse(self, value: float) -> None:
        """0..1 的说话脉冲，用于气泡轻微缩放。"""
        pulse = min(max(float(value), 0.0), 1.0)
        if abs(pulse - self._pulse) < 0.01:
            return
        self._pulse = pulse
        self.update()

    def visible_text(self) -> str:
        if not self._caption:
            return ""
        return self._caption[: max(self._revealed, 0)]

    @property
    def emotion(self) -> str:
        return emotion_of(self._caption)

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
        if self._pulse:
            center = QRectF(bubble).center()
            scale = 1.0 + PULSE_SCALE * self._pulse
            painter.translate(center)
            painter.scale(scale, scale)
            painter.translate(-center)
        path = QPainterPath()
        path.addRoundedRect(QRectF(bubble), BUBBLE_RADIUS, BUBBLE_RADIUS)
        painter.fillPath(path, QColor(*BACKGROUND_RGBA))
        painter.setPen(QColor(*EMOTION_BORDERS[self.emotion]))
        painter.drawPath(path)
        painter.setPen(QColor(*FOREGROUND_RGBA))
        painter.setFont(self._font())
        inner = bubble.adjusted(PADDING, PADDING, -PADDING, -PADDING)
        painter.drawText(inner, TEXT_FLAGS, self.visible_text())
