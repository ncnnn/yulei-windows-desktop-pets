"""透明、置顶、不抢焦点的桌宠窗口。"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QImage,
    QLinearGradient,
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
from .layout import (
    BOTTOM_EXTRA,
    PAD_X,
    TOP,
    head_box,
    window_height,
    window_width,
)
from .models import Role
from .platform_win import HTCLIENT, HTTRANSPARENT, nchittest_point
from .proximity import Rect
from .status_widget import STATUS_HEIGHT, StatusWidget
from .stick_body import DRAG, IDLE, StickAnimator, hits_pose
from .stick_render import StickRenderer

FRAME_MS = int(FRAME_SECONDS * 1000)
ALPHA_HIT_THRESHOLD = 16
MIN_OPACITY = 0.10
#: 翻转接近侧面时改用「侧影」渲染；可见宽度不低于头部宽度的 35%（此前是 15% 的薄片）。
SIDE_VIEW_THRESHOLD = 0.42
MIN_FLIP_SCALE = SIDE_VIEW_THRESHOLD
#: 火柴人默认尺寸与线宽。
DEFAULT_BODY_RATIO = 0.85
DEFAULT_LINE_WIDTH = 5.0
DEFAULT_NECK_OVERLAP = 6.0
#: 火柴人线条的命中容差（像素）：线宽越粗容差越大，视觉与手感才对得上。
STICK_HIT_FACTOR = 1.6
MIN_STICK_HIT_PX = 6.0


class PetWindow(QWidget):
    """单个桌宠窗口：人物本体 + 字幕气泡。

     Signals:
        click(role): 左键点击人物本体。
        double_click(role): 左键双击（转圈彩蛋）。
        context(role, globalPos): 右键或托盘请求菜单。
        moved(role, QPoint): 拖动后的窗口左上角屏幕坐标。
    """

    click = Signal(str)
    double_click = Signal(str)
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
        self._always_on_top = True
        self._animate_enabled = bool(animate)
        self._dragging = False
        self._drag_dirty = False
        self._drag_offset = QPoint()
        self._pixmap = QPixmap()
        self._alpha: QImage | None = None
        #: 头部可见区域在图片里的归一化包围盒 (left, top, right, bottom)，
        #: 只在换头像时算一次并缓存，运行期不重算。
        self._alpha_bounds: tuple[float, float, float, float] | None = None
        self._animation = AnimationState()
        # 火柴人躯体（默认开启，可整层关闭回到只有大头）。
        self._stick_enabled = True
        self._stick_ratio = DEFAULT_BODY_RATIO
        self._stick_line_width = DEFAULT_LINE_WIDTH
        self._stick_neck_overlap = DEFAULT_NECK_OVERLAP
        self._stick_color = "#20242b"
        self._stick_spin_axis = "flip"
        self._stick = StickAnimator()
        self._renderer = StickRenderer()
        #: 侧面用的程序化剪影（由 alpha 通道生成，换头像时重建一次）。
        self._side_pixmap: QPixmap | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle(f"桌宠-{role}")

        self._caption = CaptionWidget(self)
        self._status = StatusWidget(self)
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self.tick)

        self._apply_layout()
        # 定时器在 showEvent 里启动；未显示的窗口不跑动画，省 CPU。

    # ---------------------------------------------------------------- 布局

    def _apply_layout(self) -> None:
        """重算窗口尺寸：头部盒子不动，只把窗口向下加高给躯体让位。

        窗口底边是固定锚点——加高时向上长，脚不会沉到屏幕外。
        """
        old_bottom = self.y() + self.height()
        was_visible = self.isVisible()
        width = window_width(self._pet_size)
        content_bottom = self._content_bottom()
        height = window_height(content_bottom)
        self.setFixedSize(width, height)
        caption_height = BOTTOM_EXTRA - STATUS_HEIGHT
        self._caption.setGeometry(0, int(content_bottom), width, caption_height)
        self._status.setGeometry(0, int(content_bottom) + caption_height, width, STATUS_HEIGHT)
        if was_visible:
            self.move(self.x(), int(old_bottom - height))

    def _body_height(self) -> float:
        return self._pet_size * self._stick_ratio

    def _neck_y(self) -> float:
        """颈部挂点（窗口局部 y）：可见区域底边（下巴）向上盖住一点。"""
        box = head_box(self._pet_size)
        bounds = self._alpha_bounds or (0.0, 0.0, 1.0, 1.0)
        chin = box.top + bounds[3] * box.height
        neck = chin - self._stick_neck_overlap
        return max(box.top + box.height * 0.35, neck)

    def _neck_point(self) -> tuple[float, float]:
        return head_box(self._pet_size).center_x, self._neck_y()

    def _content_bottom(self) -> float:
        """内容底边：躯体的脚底与头部盒子底取较大者。"""
        head_bottom = float(TOP + self._pet_size)
        if not self._stick_enabled:
            return head_bottom
        return max(head_bottom, self._neck_y() + self._body_height())

    def _spin_flip(self) -> float:
        """Y 轴翻转系数：cos(自转角度)，侧面不再压成薄片。"""
        if self._stick_spin_axis != "flip":
            return 1.0
        value = math.cos(self._animation.pose.spin)
        if abs(value) < SIDE_VIEW_THRESHOLD:
            value = SIDE_VIEW_THRESHOLD if value >= 0.0 else -SIDE_VIEW_THRESHOLD
        return value

    @property
    def _side_view(self) -> bool:
        """是否已经转到接近侧面（改用侧影绘制）。"""
        if self._stick_spin_axis != "flip":
            return False
        return abs(math.cos(self._animation.pose.spin)) < SIDE_VIEW_THRESHOLD

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
        self._alpha_bounds = self._compute_alpha_bounds(self._alpha)
        self._side_pixmap = self._build_side_pixmap(self._alpha)
        # 颈部挂点依赖可见区域底边，换了头像就要重算布局。
        self._apply_layout()
        self.update()

    def pixmap(self) -> QPixmap:
        return self._pixmap

    @staticmethod
    def _build_alpha(pixmap: QPixmap) -> QImage | None:
        if pixmap.isNull():
            return None
        return pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)

    @staticmethod
    def _compute_alpha_bounds(
        image: QImage | None,
    ) -> tuple[float, float, float, float] | None:
        """可见区域的归一化包围盒（只算一次，缩到 128px 再扫）。

        原图 1200px 见方逐像素扫太慢；缩略图足以定位下巴与左右边界，
        误差在 1% 以内，用于挂点和命中区域完全够。
        """
        if image is None or image.isNull():
            return None
        sample = image.scaled(
            128,
            128,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        ).convertToFormat(QImage.Format.Format_ARGB32)
        width, height = sample.width(), sample.height()
        if width <= 0 or height <= 0:
            return None
        min_x, min_y, max_x, max_y = width, height, -1, -1
        for y in range(height):
            for x in range(width):
                if sample.pixelColor(x, y).alpha() > ALPHA_HIT_THRESHOLD:
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y
        if max_x < 0 or max_y < 0:
            return None
        return (
            min_x / width,
            min_y / height,
            (max_x + 1) / width,
            (max_y + 1) / height,
        )

    @staticmethod
    def _head_tone(image: QImage) -> QColor:
        """取头顶区域的平均色，作为侧影的填充色（头发色）。"""
        sample = image.scaled(
            48,
            48,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        ).convertToFormat(QImage.Format.Format_ARGB32)
        red = green = blue = count = 0
        top = int(sample.height() * 0.05)
        bottom = max(top + 1, int(sample.height() * 0.32))
        for y in range(top, bottom):
            for x in range(sample.width()):
                color = sample.pixelColor(x, y)
                if color.alpha() > 128:
                    red += color.red()
                    green += color.green()
                    blue += color.blue()
                    count += 1
        if count == 0:
            return QColor("#2b2f36")
        return QColor(red // count, green // count, blue // count)

    @classmethod
    def _build_side_pixmap(cls, image: QImage | None) -> QPixmap | None:
        """用 alpha 通道生成「侧后脑勺」剪影：纯色渐变 + 原图轮廓。

        这样转到侧面时看到的是一个有厚度的侧影，而不是被压成一条线。
        只在换头像时算一次，之后缓存复用。
        """
        if image is None or image.isNull():
            return None
        limit = 256
        if max(image.width(), image.height()) > limit:
            source = image.scaled(
                limit,
                limit,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            source = image
        source = source.convertToFormat(QImage.Format.Format_ARGB32)

        tone = cls._head_tone(source)
        side = QPixmap(source.size())
        side.fill(Qt.GlobalColor.transparent)
        painter = QPainter(side)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(0.0, 0.0, 0.0, float(source.height()))
        gradient.setColorAt(0.0, tone.lighter(118))
        gradient.setColorAt(0.7, tone)
        gradient.setColorAt(1.0, tone.darker(128))
        painter.fillRect(side.rect(), QBrush(gradient))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawImage(0, 0, source)
        # 补一个鼻尖凸起，让剪影读起来像侧脸而不是一根椭圆。
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tone))
        painter.drawEllipse(
            QPointF(source.width() * 0.90, source.height() * 0.56),
            source.width() * 0.10,
            source.height() * 0.07,
        )
        painter.end()
        return side

    @property
    def alpha_bounds(self) -> tuple[float, float, float, float] | None:
        return self._alpha_bounds

    # ------------------------------------------------------------ 鼠标穿透

    def nativeEvent(self, event_type, message):
        """Windows 像素级穿透：透明处返回 HTTRANSPARENT，事件直落到底层窗口。

        这是「不规则透明窗口」的关键：不靠轮询光标、也不靠 `WA_TransparentForMouseEvents`
        （那是整窗开关，连大头都点不到）。命中判定仍交给 `hit_test()`，所以穿透
        口径与视觉完全一致——只有大头像素、火柴人线条、气泡与状态胶囊算「实体」。

        **必须显式返回 HTCLIENT**：``WM_NCHITTEST`` 的返回值为 0 是 ``HTNOWHERE``，
        意思是「这一点不属于任何窗口」，鼠标按下、拖动、右键全部收不到——这正是
        v2.1.1 之后「桌宠点不动」的根因（当时命中也返回 ``(False, 0)``，等于让
        Windows 把整只桌宠当成不可交互）。

        非 Windows、或不是这条消息时交回 Qt 默认处理。
        """
        if event_type != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)
        point = nchittest_point(int(message))
        if point is None:
            # 不认识的 Windows 消息交回 Qt（返回 False = 未处理，Qt 继续默认流程）。
            return False, 0
        local = self.mapFromGlobal(QPoint(point[0], point[1]))
        if not self.hit_test(local):
            return True, HTTRANSPARENT
        return True, HTCLIENT

    def hit_test_global(self, global_pos: QPoint) -> bool:
        """屏幕坐标版的命中测试，供穿透判定与调试复用。"""
        return self.hit_test(self.mapFromGlobal(global_pos))

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
        self._stick.advance(FRAME_SECONDS)
        self._caption.set_pulse(self._animation.pulse)
        self.update()
        return pose

    # ------------------------------------------------------------ 火柴人

    @property
    def stick_enabled(self) -> bool:
        return self._stick_enabled

    @property
    def stick_state(self) -> str:
        return self._stick.state

    def set_stick_body_enabled(self, value: bool) -> None:
        if bool(value) == self._stick_enabled:
            return
        self._stick_enabled = bool(value)
        self._stick.play(IDLE)
        self._apply_layout()
        self.update()

    def set_stick_body_ratio(self, ratio: float) -> None:
        self._stick_ratio = min(max(float(ratio), 0.4), 1.4)
        self._apply_layout()
        self.update()

    def set_stick_line_width(self, width: float) -> None:
        self._stick_line_width = min(max(float(width), 2.0), 12.0)
        self._renderer.configure(self._stick_color, self._stick_line_width)
        self.update()

    def set_stick_color(self, color: str) -> None:
        self._stick_color = color
        self._renderer.configure(self._stick_color, self._stick_line_width)
        self.update()

    def set_stick_neck_overlap(self, pixels: float) -> None:
        self._stick_neck_overlap = min(max(float(pixels), 0.0), 40.0)
        self._apply_layout()
        self.update()

    def set_stick_spin_axis(self, axis: str) -> None:
        self._stick_spin_axis = "roll" if axis == "roll" else "flip"
        self.update()

    def play_stick_action(self, state: str, seconds: float = 2.0) -> None:
        """播放一次性动作（wave / dance / jump），播完自动回到待机。"""
        if not self._stick_enabled:
            return
        self._stick.play(state, seconds)
        self.update()

    def set_stick_lean(self, radians: float) -> None:
        self._stick.set_lean(radians)
        self.update()

    def jump(self) -> None:
        """点击反馈：播放一次跳跃关键帧。"""
        self._animation.jump()
        self.update()

    def shake(self) -> None:
        """出错反馈：播放一次抖动关键帧。"""
        self._animation.shake()
        self.update()

    def nod(self) -> None:
        """回应反馈：播放一次点头关键帧。"""
        self._animation.nod()
        self.update()

    def wave(self) -> None:
        """打招呼：播放一次挥手关键帧。"""
        self._animation.wave()
        self.update()

    def spin(self) -> None:
        """双击彩蛋：原地转一圈。"""
        self._animation.spin()
        self.update()

    def set_animating(self, value: bool) -> None:
        """总开关；关闭后即使窗口显示也不再跑 30fps 动画。"""
        self._animate_enabled = bool(value)
        if self._animate_enabled and self.isVisible():
            self._timer.start()
        else:
            self._timer.stop()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        if self._animate_enabled:
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        # 隐藏时停掉动画定时器，省 CPU；再次显示会自动恢复。
        self._timer.stop()
        super().hideEvent(event)

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
        # 翻转模式下自转由 scaleX 表达，头部只保留倾斜角，避免叠加两次。
        angle = (
            pose.render_angle_degrees if self._stick_spin_axis == "roll" else pose.angle_degrees
        )
        return (
            QTransform()
            .translate(center_x, anchor_y)
            .rotate(angle)
            .scale(1.0, pose.compression)
            .translate(-center_x, -anchor_y)
        )

    def _display_transform(self) -> QTransform:
        """命中测试与绘制共用的完整变换（含 Y 轴翻转）。"""
        base = self._character_transform()
        flip = self._spin_flip()
        if flip == 1.0:
            return base
        box = self._character_box()
        center_x = box.left() + box.width() / 2.0
        outer = QTransform()
        outer.translate(center_x, 0.0)
        outer.scale(flip, 1.0)
        outer.translate(-center_x, 0.0)
        return outer * base

    def paintEvent(self, event: QPaintEvent) -> None:
        """分层绘制：躯体 → 头部 → 颈部接缝，人物整体再做 Y 轴翻转。

        窗口**不画任何底**：没画的像素就是全透明，直接透出桌面。这也是穿透
        判定能只看「画出来的东西」的前提。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._pixmap.isNull():
            return

        box = self._character_box()
        center_x = box.left() + box.width() / 2.0
        neck_y = self._neck_y()
        unit = self._body_height()

        flip = self._spin_flip()
        if flip != 1.0:
            painter.translate(center_x, 0.0)
            painter.scale(flip, 1.0)
            painter.translate(-center_x, 0.0)

        if self._stick_enabled:
            self._renderer.draw_body(
                painter,
                self._stick.pose(),
                center_x=center_x,
                neck_y=neck_y,
                unit=unit,
            )

        painter.save()
        painter.setTransform(self._character_transform(), True)
        if self._side_view and self._side_pixmap is not None:
            painter.drawPixmap(box, self._side_pixmap, QRectF(self._side_pixmap.rect()))
        else:
            painter.drawPixmap(box, self._pixmap, QRectF(self._pixmap.rect()))
        painter.restore()

        if self._stick_enabled:
            self._renderer.draw_seam(
                painter,
                center_x=center_x,
                neck_y=neck_y,
                unit=unit,
            )

    # ---------------------------------------------------------------- 字幕

    def set_caption(self, text: str | None) -> None:
        self._caption.set_caption(text)

    def caption(self) -> str:
        return self._caption.caption()

    @property
    def status_widget(self) -> StatusWidget:
        return self._status

    def set_status_text(self, text: str | None) -> None:
        """常驻状态条（番茄钟倒计时）；与对话气泡互不覆盖。"""
        self._status.set_text(text)

    def status_text(self) -> str:
        return self._status.text()

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

    def set_always_on_top(self, value: bool) -> None:
        """切换置顶；Qt 要求重设窗口标志后重新显示。"""
        value = bool(value)
        if value == self._always_on_top:
            return
        self._always_on_top = value
        flags = self.windowFlags()
        if value:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        visible = self.isVisible()
        self.setWindowFlags(flags)
        if visible:
            self.show()
            self.raise_()

    @property
    def always_on_top(self) -> bool:
        return self._always_on_top

    def set_locked(self, value: bool) -> None:
        self._locked = bool(value)
        if self._locked:
            self._dragging = False
            self._stick.play(IDLE)

    @property
    def locked(self) -> bool:
        return self._locked

    @property
    def dragging(self) -> bool:
        """是否正在被拖动；自动游走据此避开用户的拖拽。"""
        return self._dragging

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
            self._stick.play(IDLE)

    @property
    def click_through(self) -> bool:
        return self._click_through

    def request_context(self, global_pos: QPoint | None = None) -> None:
        """托盘等外部入口请求右键菜单。"""
        position = global_pos if global_pos is not None else self.mapToGlobal(QPoint(0, 0))
        self.context.emit(self._role, position)

    def hit_test(self, local: QPoint) -> bool:
        """命中测试 = 「这一像素画了东西吗」。

        只有四类区域算实体：大头的 PNG alpha、火柴人的线条、正在显示的气泡、
        正在显示的状态胶囊。其余一律视为透明——主窗口的穿透判定（HTTRANSPARENT）
        也用这个函数，所以视觉与点击口径永远一致。
        """
        if self._click_through:
            return False
        if self._hit_caption(local) or self._hit_status(local):
            return True
        point = QPointF(local)
        if self._hit_head(point):
            return True
        return self._stick_enabled and self._hit_stick(point)

    def _hit_caption(self, local: QPoint) -> bool:
        """只有气泡本体（含文字时的圆角矩形）可点，整条字幕区不算。"""
        if not self._caption.caption():
            return False
        bubble = self._caption.bubble_rect()
        if not bubble.isValid():
            return False
        return bubble.translated(self._caption.geometry().topLeft()).contains(local)

    def _hit_status(self, local: QPoint) -> bool:
        if not self._status.text() or not self._status.isVisible():
            return False
        pill = self._status.pill_rect()
        if not pill.isValid():
            return False
        return pill.translated(self._status.geometry().topLeft()).contains(local)

    def _hit_head(self, point: QPointF) -> bool:
        box = self._character_box()
        transform = self._display_transform()
        inverse, invertible = transform.inverted()
        if not invertible:
            return False
        mapped = inverse.map(point)
        if not box.contains(mapped):
            return False
        if self._alpha is None:
            return True
        px = int((mapped.x() - box.left()) / box.width() * self._alpha.width())
        py = int((mapped.y() - box.top()) / box.height() * self._alpha.height())
        if not (0 <= px < self._alpha.width() and 0 <= py < self._alpha.height()):
            return False
        return self._alpha.pixelColor(px, py).alpha() >= ALPHA_HIT_THRESHOLD

    def _hit_stick(self, point: QPointF) -> bool:
        """按骨架线段判命中：手臂、腿部也真的能点，而不是只有一个矩形带。

        把光标点换到归一化骨架坐标（Y 轴翻转时先反镜像），再算点到线段的
        距离；容差随线宽放大，握着线条边缘也能拖。
        """
        center_x, neck_y = self._neck_point()
        unit = self._body_height()
        if unit <= 0.0:
            return False
        flip = self._spin_flip()
        x = point.x()
        if flip not in (0.0, 1.0):
            x = center_x + (x - center_x) / flip
        nx = (x - center_x) / unit
        ny = (point.y() - neck_y) / unit
        tolerance = max(MIN_STICK_HIT_PX, self._stick_line_width * STICK_HIT_FACTOR) / unit
        return hits_pose(self._stick.pose(), nx, ny, tolerance)

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
            if self._stick_enabled:
                self._stick.play(DRAG)
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._click_through:
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.hit_test(event.position().toPoint())
        ):
            self.double_click.emit(self._role)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

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
        if was_dragging or self._stick.state == DRAG:
            self._stick.play(IDLE)
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
