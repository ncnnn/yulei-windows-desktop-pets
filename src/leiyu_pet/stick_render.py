"""火柴人躯体的绘制层：把归一化姿态画到 QPainter 上。

性能约定：画笔与画刷在 ``configure()`` 时创建一次并复用，每帧只做
``drawLine`` / ``drawEllipse``，不重建 QPen/QBrush，也不构建 QPainterPath。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen

from .stick_body import StickPose

DEFAULT_COLOR = "#20242b"


class StickRenderer:
    def __init__(self) -> None:
        self._pen = QPen()
        self._pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self._pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._joint_brush = QBrush(QColor(DEFAULT_COLOR))
        self._seam_brush = QBrush()
        self._line_width = 5.0
        self._color = QColor(DEFAULT_COLOR)
        self._joint_radius = 2.6
        self.configure(DEFAULT_COLOR, self._line_width)

    # ------------------------------------------------------------ 配置

    def configure(self, color: str, line_width: float) -> None:
        width = max(1.0, float(line_width))
        parsed = QColor(color)
        if not parsed.isValid():
            parsed = QColor(DEFAULT_COLOR)
        self._line_width = width
        self._color = parsed
        self._pen.setColor(parsed)
        self._pen.setWidthF(width)
        self._joint_brush = QBrush(parsed)
        self._joint_radius = max(1.6, width * 0.55)
        seam = QColor(parsed)
        seam.setAlpha(90)
        self._seam_brush = QBrush(seam)

    @property
    def line_width(self) -> float:
        return self._line_width

    @property
    def color(self) -> QColor:
        return self._color

    # ------------------------------------------------------------ 绘制

    def draw_body(
        self,
        painter: QPainter,
        pose: StickPose,
        *,
        center_x: float,
        neck_y: float,
        unit: float,
    ) -> None:
        """画躯干、四肢与关节；调用方负责先画这一层、再画头部。"""
        if unit <= 0.0:
            return

        def point(p: tuple[float, float]) -> QPointF:
            return QPointF(center_x + p[0] * unit, neck_y + p[1] * unit)

        painter.setPen(self._pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        neck = point(pose.neck)
        hip = point(pose.hip)
        painter.drawLine(neck, hip)

        for limb in pose.arms:
            painter.drawLine(point(limb.start), point(limb.joint))
            painter.drawLine(point(limb.joint), point(limb.end))
        for limb in pose.legs:
            painter.drawLine(point(limb.start), point(limb.joint))
            painter.drawLine(point(limb.joint), point(limb.end))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._joint_brush)
        radius = self._joint_radius
        for limb in (*pose.arms, *pose.legs):
            for joint in (limb.start, limb.joint, limb.end):
                painter.drawEllipse(point(joint), radius, radius)

    def draw_seam(
        self,
        painter: QPainter,
        *,
        center_x: float,
        neck_y: float,
        unit: float,
    ) -> None:
        """在头部底下压一层淡阴影，避免头「浮」在身体上。"""
        if unit <= 0.0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._seam_brush)
        painter.drawEllipse(
            QPointF(center_x, neck_y + unit * 0.02),
            unit * 0.12,
            unit * 0.05,
        )
