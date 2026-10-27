"""对话开场的「决斗特效」：连线中点闪一次 VS，约 1 秒淡出。

注意命名：这里是**决斗动画**（纯视觉特效窗口），与**决战模式**（逐句音量
阶梯）不是一回事。

窗口属性：无边框、置顶、不接受焦点、鼠标穿透、不占任务栏。同一时刻只允许
一个特效，后来的请求直接丢弃（由调用方记日志）。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

DUEL_SIZE = 190
DUEL_DURATION = 1.0
FRAME_MS = 16
#: 前 60% 的时间缓动跟随中点，进入淡出后不再移动。
FOLLOW_UNTIL = 0.6
#: 每帧向目标靠近的比例（不做逐帧硬跟）。
FOLLOW_FACTOR = 0.25

GOLD = QColor(255, 204, 64)
RED = QColor(238, 76, 76)
BLUE = QColor(74, 144, 255)
WHITE = QColor(255, 255, 255)


class DuelEffect(QWidget):
    finished = Signal()

    def __init__(self, center_provider: Callable[[], QPoint | None] | None = None) -> None:
        # 顶层窗口：不能挂父窗口，否则会被父窗口裁剪。
        super().__init__(None)
        self._center_provider = center_provider
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("决斗特效")
        self.setFixedSize(DUEL_SIZE, DUEL_SIZE)

        self._progress = 1.0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def progress(self) -> float:
        return self._progress

    def play_at(self, center: QPoint) -> bool:
        """在给定屏幕坐标的中心播放一次；正在播放时返回 False。"""
        if self._playing:
            return False
        self._progress = 0.0
        self._playing = True
        self.move(center.x() - DUEL_SIZE // 2, center.y() - DUEL_SIZE // 2)
        self.show()
        self.raise_()
        self._timer.start()
        self.update()
        return True

    def _tick(self) -> None:
        self._step(FRAME_MS / 1000.0)

    def _step(self, seconds: float) -> None:
        """推进动画；单独暴露给测试用（不必真的等一秒）。"""
        if not self._playing:
            return
        self._progress = min(1.0, self._progress + float(seconds) / DUEL_DURATION)
        self._follow_target()
        self.update()
        if self._progress >= 1.0:
            self._finish()

    def _follow_target(self) -> None:
        """缓动跟随两只桌宠的连线中点；淡出阶段冻结，避免抖动。"""
        if self._progress >= FOLLOW_UNTIL or self._center_provider is None:
            return
        target = self._center_provider()
        if target is None:
            return
        dx = target.x() - (self.x() + DUEL_SIZE // 2)
        dy = target.y() - (self.y() + DUEL_SIZE // 2)
        if abs(dx) <= 1 and abs(dy) <= 1:
            return
        self.move(
            self.x() + int(dx * FOLLOW_FACTOR),
            self.y() + int(dy * FOLLOW_FACTOR),
        )

    def _finish(self) -> None:
        self._timer.stop()
        self._playing = False
        self.hide()
        self.finished.emit()

    def stop(self) -> None:
        if not self._playing:
            return
        self._timer.stop()
        self._playing = False
        self.hide()

    # ---------------------------------------------------------------- 绘制

    def _opacity(self) -> float:
        p = self._progress
        if p <= 0.10:
            return p / 0.10
        if p >= 0.60:
            return max(0.0, (1.0 - p) / 0.40)
        return 1.0

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if not self._playing:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        alpha = self._opacity()
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        painter.setOpacity(alpha)

        # 冲击环：由内向外扩散并变细
        for index, (scale, width) in enumerate(((0.30, 6.0), (0.45, 3.0))):
            ring_alpha = int(230 * (1.0 - self._progress) * (1.0 - index * 0.35))
            pen = QPen(QColor(GOLD.red(), GOLD.green(), GOLD.blue(), max(0, ring_alpha)))
            pen.setWidthF(width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = self.width() * (scale + 0.35 * self._progress)
            painter.drawEllipse(center, radius, radius)

        # 左右两道闪电
        painter.setPen(Qt.PenStyle.NoPen)
        self._draw_bolt(painter, center, RED, -1)
        self._draw_bolt(painter, center, BLUE, 1)

        # VS 文字，先放大再回落到正常
        pop = 1.0 + 0.25 * max(0.0, 0.35 - self._progress) / 0.35
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(28.0 * pop)
        painter.setFont(font)
        painter.setPen(QPen(QColor(0, 0, 0, 120)))
        painter.drawText(
            QRectF(2.0, 2.0, self.width(), self.height()),
            Qt.AlignmentFlag.AlignCenter,
            "VS",
        )
        painter.setPen(QPen(WHITE))
        painter.drawText(
            QRectF(0.0, 0.0, self.width(), self.height()),
            Qt.AlignmentFlag.AlignCenter,
            "VS",
        )

    def _draw_bolt(self, painter: QPainter, center: QPointF, color: QColor, side: int) -> None:
        span = self.width() * 0.34
        top = center.y() - self.height() * 0.18
        bottom = center.y() + self.height() * 0.18
        start_x = center.x() + side * self.width() * 0.06
        points = [
            QPointF(start_x, top),
            QPointF(start_x + side * span * 0.55, center.y() - self.height() * 0.03),
            QPointF(start_x + side * span * 0.25, center.y() + self.height() * 0.01),
            QPointF(start_x + side * span * 0.85, bottom),
        ]
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF(points))
