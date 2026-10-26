"""透明、置顶、不抢焦点的桌宠窗口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QWidget

from .animation import (
    DEFAULT_PET_SIZE,
    FRAME_SECONDS,
    AnimationState,
    Pose,
    clamp_pet_size,
)
from .caption_widget import CaptionWidget
from .models import Role
from .proximity import Rect

PAD_X = 48
TOP = 16
BOTTOM_EXTRA = 112

FRAME_MS = int(FRAME_SECONDS * 1000)
ALPHA_HIT_THRESHOLD = 16
MIN_OPACITY = 0.10


class PetWindow(QWidget):
    """单个桌宠窗口：人物本体 + 字幕气泡。

     Signals:
        click(role): 左键点击人物本体。
        context(role, globalPos): 右键或托盘请求菜单。
        moved(role, QPoint): 拖动后的窗口左上角屏幕坐标。
    """

    click = Signal(str)
    context = Signal(str, QPoint)
    moved = Signal(str, QPoint)

    def __init__(
        self,
        role: Role = "lei",
        *,
        pet_size: int = DEFAULT_PET_SIZE,
        animate: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._role: Role = role
        self._pet_size = clamp_pet_size(pet_size)
        self._locked = False
        self._shift_drag = False
        self._click_through = False
        self._opacity = 1.0
        self._dragging = False
        self._drag_dirty = False
        self._drag_offset = QPoint()
        self._pixmap = QPixmap()
        self._alpha: QImage | None = None
        self._animation = AnimationState()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle(f"桌宠-{role}")

        self._caption = CaptionWidget(self)
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self.tick)

        self._apply_layout()
        if animate:
            self._timer.start()

    # ---------------------------------------------------------------- 布局

    def _apply_layout(self) -> None:
        width = self._pet_size + 2 * PAD_X
        height = self._pet_size + TOP + BOTTOM_EXTRA
        self.setFixedSize(width, height)
        self._caption.setGeometry(0, TOP + self._pet_size, width, BOTTOM_EXTRA)

    @property
    def role(self) -> Role:
        return self._role

    @property
    def pet_size(self) -> int:
        return self._pet_size

    def set_pet_size(self, value: int) -> None:
        size = clamp_pet_size(value)
        if size == self._pet_size:
            return
        self._pet_size = size
        self._apply_layout()
        self.update()

    def _character_box(self) -> QRectF:
        """绘制用的人物框（含 bob、跳跃与抖动偏移，未旋转/未压缩）。"""
        pose = self._animation.pose
        return QRectF(
            PAD_X + pose.offset_x,
            TOP - pose.bob - pose.offset_y,
            self._pet_size,
            self._pet_size,
        )

    def character_rect(self) -> QRect:
        """人物本体的窗口局部整数矩形（含 bob 偏移，未旋转/未压缩）。"""
        return self._character_box().toRect()

    def face_rect_global(self) -> Rect:
        """人物可见区域的屏幕坐标包围盒，供 proximity 判定使用。"""
        transform = self._character_transform()
        box = self._character_box()
        corners = (
            QPointF(box.left(), box.top()),
            QPointF(box.right(), box.top()),
            QPointF(box.right(), box.bottom()),
            QPointF(box.left(), box.bottom()),
        )
        mapped = [transform.map(corner) for corner in corners]
        xs = [point.x() for point in mapped]
        ys = [point.y() for point in mapped]
        origin = self.mapToGlobal(QPoint(0, 0))
        return Rect(
            origin.x() + min(xs),
            origin.y() + min(ys),
            max(xs) - min(xs),
            max(ys) - min(ys),
        )

    # ---------------------------------------------------------------- 素材

    def load_image(self, path: str | Path) -> bool:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self.set_pixmap(pixmap)
        return True

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = QPixmap(pixmap)
        self._alpha = self._build_alpha(self._pixmap)
        self.update()

    def pixmap(self) -> QPixmap:
        return self._pixmap

    @staticmethod
    def _build_alpha(pixmap: QPixmap) -> QImage | None:
        if pixmap.isNull():
            return None
        return pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)

    # ---------------------------------------------------------------- 动画

    @property
    def animation(self) -> AnimationState:
        return self._animation

    @property
    def pose(self) -> Pose:
        return self._animation.pose

    def tick(self) -> Pose:
        """推进一帧动画并重绘，同时把说话脉冲传给字幕气泡。"""
        pose = self._animation.advance()
        self._caption.set_pulse(self._animation.pulse)
        self.update()
        return pose

    def jump(self) -> None:
        """点击反馈：播放一次跳跃关键帧。"""
        self._animation.jump()
        self.update()

    def shake(self) -> None:
        """出错反馈：播放一次抖动关键帧。"""
        self._animation.shake()
        self.update()

    def set_animating(self, value: bool) -> None:
        if value:
            self._timer.start()
        else:
            self._timer.stop()

    def set_speaking(self, value: bool) -> None:
        self._animation.set_speaking(value)
        if not value:
            self.update()

    @property
    def speaking(self) -> bool:
        return self._animation.speaking

    def set_tilt(self, radians: float) -> None:
        self._animation.set_target_angle(radians)
        self.update()

    @property
    def tilt(self) -> float:
        return self._animation.target_angle

    def set_reduce_motion(self, value: bool) -> None:
        self._animation.set_reduce_motion(value)
        self.update()

    @property
    def reduce_motion(self) -> bool:
        return self._animation.reduce_motion

    def _character_transform(self) -> QTransform:
        pose = self._animation.pose
        box = self._character_box()
        center_x = box.left() + box.width() / 2.0
        anchor_y = box.bottom()
        return (
            QTransform()
            .translate(center_x, anchor_y)
            .rotate(pose.angle_degrees)
            .scale(1.0, pose.compression)
            .translate(-center_x, -anchor_y)
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._pixmap.isNull():
            return
        box = self._character_box()
        pose = self._animation.pose
        center_x = box.left() + box.width() / 2.0
        anchor_y = box.bottom()
        painter.translate(center_x, anchor_y)
        painter.rotate(pose.angle_degrees)
        painter.scale(1.0, pose.compression)
        painter.translate(-center_x, -anchor_y)
        painter.drawPixmap(box, self._pixmap, QRectF(self._pixmap.rect()))

    # ---------------------------------------------------------------- 字幕

    def set_caption(self, text: str | None) -> None:
        self._caption.set_caption(text)

    def caption(self) -> str:
        return self._caption.caption()

    @property
    def caption_widget(self) -> CaptionWidget:
        return self._caption

    # ---------------------------------------------------------------- 交互

    def set_opacity(self, value: float) -> None:
        self._opacity = max(MIN_OPACITY, min(1.0, float(value)))
        self.setWindowOpacity(self._opacity)

    @property
    def opacity(self) -> float:
        return self._opacity

    def set_locked(self, value: bool) -> None:
        self._locked = bool(value)
        if self._locked:
            self._dragging = False

    @property
    def locked(self) -> bool:
        return self._locked

    def set_shift_drag(self, value: bool) -> None:
        self._shift_drag = bool(value)
        if self._shift_drag:
            self._dragging = False

    @property
    def shift_drag(self) -> bool:
        return self._shift_drag

    def set_click_through(self, value: bool) -> None:
        self._click_through = bool(value)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, self._click_through)
        if self._click_through:
            self._dragging = False

    @property
    def click_through(self) -> bool:
        return self._click_through

    def request_context(self, global_pos: QPoint | None = None) -> None:
        """托盘等外部入口请求右键菜单。"""
        position = global_pos if global_pos is not None else self.mapToGlobal(QPoint(0, 0))
        self.context.emit(self._role, position)

    def hit_test(self, local: QPoint) -> bool:
        """命中测试：字幕气泡可拖，人物本体按 PNG alpha 逐像素判定。"""
        if self._click_through:
            return False
        if self._caption.caption() and self._caption.geometry().contains(local):
            return True
        box = self._character_box()
        if self._alpha is None:
            return box.contains(QPointF(local))
        transform = self._character_transform()
        inverse, invertible = transform.inverted()
        if not invertible:
            return False
        point = inverse.map(QPointF(local))
        if not box.contains(point):
            return False
        px = int((point.x() - box.left()) / box.width() * self._alpha.width())
        py = int((point.y() - box.top()) / box.height() * self._alpha.height())
        if not (0 <= px < self._alpha.width() and 0 <= py < self._alpha.height()):
            return False
        return self._alpha.pixelColor(px, py).alpha() >= ALPHA_HIT_THRESHOLD

    def _can_drag(self, event: QMouseEvent) -> bool:
        if self._locked:
            return False
        if self._shift_drag:
            return bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._click_through:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.context.emit(self._role, event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        local = event.position().toPoint()
        if not self.hit_test(local):
            return
        if self._can_drag(event):
            self._dragging = True
            self._drag_dirty = False
            self._drag_offset = local
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging:
            return
        target = event.globalPosition().toPoint() - self._drag_offset
        if target != self.pos():
            self.move(target)
            self._drag_dirty = True
            self.moved.emit(self._role, self.pos())
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        was_dragging = self._dragging
        self._dragging = False
        if not was_dragging:
            if self.hit_test(event.position().toPoint()):
                self.click.emit(self._role)
        elif not self._drag_dirty:
            self.click.emit(self._role)
        self._drag_dirty = False
        event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        super().closeEvent(event)
