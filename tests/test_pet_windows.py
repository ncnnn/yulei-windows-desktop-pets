"""PySide6 桌宠窗口层测试：窗口属性、信号、拖动、动画与字幕。"""

from __future__ import annotations

import ctypes
import math
import os
from ctypes import wintypes
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from leiyu_pet import pet_window as pet_window_module
from leiyu_pet import platform_win
from leiyu_pet.animation import (
    DEFAULT_PET_SIZE,
    MAX_PET_SIZE,
    MIN_PET_SIZE,
    SPEAK_PHASE_STEP,
    AnimationState,
    clamp_pet_size,
    ease_towards,
    speaking_pulse,
)
from leiyu_pet.caption_widget import PADDING, CaptionWidget
from leiyu_pet.pet_window import BOTTOM_EXTRA, PAD_X, STATUS_HEIGHT, TOP, PetWindow
from leiyu_pet.platform_win import HTCLIENT, HTTRANSPARENT

# 必须在 QApplication 创建之前生效：无显示环境下使用 offscreen 插件，避免弹出可见窗口。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

IMAGE_SIZE = 64


# --------------------------------------------------------------------- 辅助


def write_pet_png(path: Path, *, radius: int = IMAGE_SIZE // 2 - 2) -> Path:
    """运行时生成一张小透明 PNG：中间不透明圆，四周全透明。"""
    image = QImage(IMAGE_SIZE, IMAGE_SIZE, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 80, 80, 255))
    offset = IMAGE_SIZE // 2 - radius
    painter.drawEllipse(offset, offset, radius * 2, radius * 2)
    painter.end()
    assert image.save(str(path), "PNG")
    return path


def center_point(window: PetWindow) -> QPoint:
    size = window.pet_size
    return QPoint(PAD_X + size // 2, TOP + size // 2)


def send(window: PetWindow, kind: QEvent.Type, local: QPoint, **kwargs) -> None:
    button = kwargs.get("button", Qt.MouseButton.LeftButton)
    buttons = kwargs.get("buttons", button)
    modifiers = kwargs.get("modifiers", Qt.KeyboardModifier.NoModifier)
    event = QMouseEvent(
        kind,
        QPointF(local),
        QPointF(window.mapToGlobal(local)),
        button,
        buttons,
        modifiers,
    )
    QApplication.sendEvent(window, event)


def press(window: PetWindow, local: QPoint, **kwargs) -> None:
    send(window, QEvent.Type.MouseButtonPress, local, **kwargs)


def move_to(window: PetWindow, local: QPoint, **kwargs) -> None:
    kwargs.setdefault("button", Qt.MouseButton.NoButton)
    kwargs.setdefault("buttons", Qt.MouseButton.LeftButton)
    send(window, QEvent.Type.MouseMove, local, **kwargs)


def release(window: PetWindow, local: QPoint, **kwargs) -> None:
    kwargs.setdefault("buttons", Qt.MouseButton.NoButton)
    send(window, QEvent.Type.MouseButtonRelease, local, **kwargs)


def has_flag(flags: Qt.WindowType, flag: Qt.WindowType) -> bool:
    return (flags & flag) == flag


@pytest.fixture(autouse=True)
def _require_qapp(qapp: QApplication) -> None:
    """任何 Qt 对象创建之前都必须先有 QApplication。"""


@pytest.fixture
def pet(tmp_path: Path, qtbot) -> PetWindow:
    window = PetWindow("lei", animate=False)
    qtbot.addWidget(window)
    window.move(200, 300)
    assert window.load_image(write_pet_png(tmp_path / "lei.png"))
    yield window
    window.close()


# ------------------------------------------------------------- 窗口属性


def test_window_is_frameless_always_on_top_tool(pet: PetWindow) -> None:
    flags = pet.windowFlags()
    assert has_flag(flags, Qt.WindowType.FramelessWindowHint)
    assert has_flag(flags, Qt.WindowType.WindowStaysOnTopHint)
    assert has_flag(flags, Qt.WindowType.WindowDoesNotAcceptFocus)
    assert pet.windowType() == Qt.WindowType.Tool


def test_window_is_translucent_and_unfocusable(pet: PetWindow) -> None:
    assert pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert pet.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
    assert pet.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_window_size_covers_character_and_caption(pet: PetWindow) -> None:
    assert pet.pet_size == DEFAULT_PET_SIZE
    assert pet.width() == DEFAULT_PET_SIZE + 2 * PAD_X
    # 躯体让窗口向下加高，头部盒子仍在原来的位置与大小。
    content_bottom = pet._content_bottom()
    assert pet.height() == int(content_bottom) + BOTTOM_EXTRA
    assert pet.height() > DEFAULT_PET_SIZE + TOP + BOTTOM_EXTRA
    caption = pet.caption_widget.geometry()
    assert caption.y() == int(content_bottom)
    assert caption.height() == BOTTOM_EXTRA - STATUS_HEIGHT
    # 状态条在字幕下方单独一条，与对话气泡分开
    assert pet.status_widget.geometry().y() == caption.y() + caption.height()
    assert pet.status_widget.height() == STATUS_HEIGHT


def test_pet_size_is_clamped(pet: PetWindow) -> None:
    pet.set_pet_size(10)
    assert pet.pet_size == MIN_PET_SIZE
    assert pet.width() == MIN_PET_SIZE + 2 * PAD_X
    pet.set_pet_size(9999)
    assert pet.pet_size == MAX_PET_SIZE
    assert pet.width() == MAX_PET_SIZE + 2 * PAD_X
    assert clamp_pet_size(220.9) == 220


def test_opacity_is_clamped(pet: PetWindow) -> None:
    pet.set_opacity(0.5)
    assert pet.opacity == pytest.approx(0.5)
    assert pet.windowOpacity() == pytest.approx(0.5, abs=0.01)
    pet.set_opacity(5.0)
    assert pet.opacity == pytest.approx(1.0)
    pet.set_opacity(0.0)
    assert pet.opacity == pytest.approx(0.10)


# ----------------------------------------------------------------- 信号


def test_left_click_emits_click_with_role(pet: PetWindow, qtbot) -> None:
    seen: list[str] = []
    pet.click.connect(seen.append)
    spot = center_point(pet)
    with qtbot.waitSignal(pet.click, timeout=1000):
        press(pet, spot)
        release(pet, spot)
    assert seen == ["lei"]


def test_click_outside_character_is_ignored(pet: PetWindow) -> None:
    seen: list[str] = []
    pet.click.connect(seen.append)
    press(pet, QPoint(2, 2))
    release(pet, QPoint(2, 2))
    assert seen == []


def test_right_click_emits_context_with_global_pos(pet: PetWindow, qtbot) -> None:
    seen: list[tuple[str, QPoint]] = []
    pet.context.connect(lambda role, pos: seen.append((role, pos)))
    spot = center_point(pet)
    with qtbot.waitSignal(pet.context, timeout=1000):
        press(pet, spot, button=Qt.MouseButton.RightButton)
    assert seen[0][0] == "lei"
    assert seen[0][1] == pet.mapToGlobal(spot)


def test_request_context_uses_window_origin(pet: PetWindow) -> None:
    seen: list[tuple[str, QPoint]] = []
    pet.context.connect(lambda role, pos: seen.append((role, pos)))
    pet.request_context()
    assert seen == [("lei", pet.pos())]
    pet.request_context(QPoint(9, 9))
    assert seen[1] == ("lei", QPoint(9, 9))


# ----------------------------------------------------------------- 拖动


def test_drag_moves_window_and_emits_moved(pet: PetWindow) -> None:
    seen: list[tuple[str, QPoint]] = []
    pet.moved.connect(lambda role, pos: seen.append((role, pos)))
    origin = pet.pos()
    press(pet, center_point(pet))
    move_to(pet, center_point(pet) + QPoint(40, -25))
    release(pet, center_point(pet) + QPoint(40, -25))
    assert pet.pos() == origin + QPoint(40, -25)
    assert seen == [("lei", origin + QPoint(40, -25))]


def test_drag_does_not_emit_click(pet: PetWindow) -> None:
    clicks: list[str] = []
    pet.click.connect(clicks.append)
    press(pet, center_point(pet))
    move_to(pet, center_point(pet) + QPoint(10, 10))
    release(pet, center_point(pet) + QPoint(10, 10))
    assert clicks == []


def test_locked_window_cannot_move_but_still_clicks(pet: PetWindow) -> None:
    pet.set_locked(True)
    moves: list[QPoint] = []
    clicks: list[str] = []
    pet.moved.connect(lambda _role, pos: moves.append(pos))
    pet.click.connect(clicks.append)
    origin = pet.pos()
    spot = center_point(pet)
    press(pet, spot)
    move_to(pet, spot + QPoint(30, 30))
    release(pet, spot)
    assert pet.pos() == origin
    assert moves == []
    assert clicks == ["lei"]


def test_shift_drag_requires_shift_modifier(pet: PetWindow) -> None:
    pet.set_shift_drag(True)
    origin = pet.pos()
    spot = center_point(pet)
    press(pet, spot)
    move_to(pet, spot + QPoint(30, 30))
    release(pet, spot + QPoint(30, 30))
    assert pet.pos() == origin

    press(pet, spot, modifiers=Qt.KeyboardModifier.ShiftModifier)
    move_to(pet, spot + QPoint(30, 30), modifiers=Qt.KeyboardModifier.ShiftModifier)
    release(pet, spot + QPoint(30, 30))
    assert pet.pos() == origin + QPoint(30, 30)


def test_unlock_after_lock_restores_dragging(pet: PetWindow) -> None:
    pet.set_locked(True)
    pet.set_locked(False)
    origin = pet.pos()
    spot = center_point(pet)
    press(pet, spot)
    move_to(pet, spot + QPoint(12, 8))
    release(pet, spot + QPoint(12, 8))
    assert pet.pos() == origin + QPoint(12, 8)


# ---------------------------------------------------------- 透明命中 / 穿透


def test_hit_test_uses_png_alpha(pet: PetWindow) -> None:
    assert pet.hit_test(center_point(pet)) is True
    assert pet.hit_test(QPoint(PAD_X + 2, TOP + 2)) is False
    assert pet.hit_test(QPoint(5, 5)) is False


def test_click_through_disables_and_restores_hits(pet: PetWindow) -> None:
    pet.set_click_through(True)
    assert pet.click_through is True
    assert pet.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert pet.hit_test(center_point(pet)) is False
    pet.set_click_through(False)
    assert pet.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is False
    assert pet.hit_test(center_point(pet)) is True


def test_caption_area_is_draggable(pet: PetWindow) -> None:
    pet.set_caption("你好，世界")
    inside = QPoint(pet.width() // 2, int(pet._content_bottom()) + 10)
    assert pet.hit_test(inside) is True
    pet.set_caption("")
    assert pet.hit_test(inside) is False


def test_missing_image_falls_back_to_character_rect(qtbot) -> None:
    window = PetWindow("yu", animate=False)
    qtbot.addWidget(window)
    assert window.hit_test(center_point(window)) is True
    assert window.hit_test(QPoint(4, 4)) is False
    window.close()


def test_load_image_rejects_missing_file(tmp_path: Path, qtbot) -> None:
    window = PetWindow("lei", animate=False)
    qtbot.addWidget(window)
    assert window.load_image(tmp_path / "nope.png") is False
    assert window.pixmap().isNull()
    window.close()


# ----------------------------------------------------------------- 动画


def test_ease_towards_and_pulse_helpers() -> None:
    assert ease_towards(0.0, 1.0) == pytest.approx(0.22)
    assert ease_towards(0.0, 1.0, 0.5) == pytest.approx(0.5)
    assert speaking_pulse(0.0) == pytest.approx(0.0)
    assert speaking_pulse(math.pi / 2) == pytest.approx(0.5)
    assert speaking_pulse(math.pi) == pytest.approx(1.0)


def test_animation_state_eases_towards_target() -> None:
    state = AnimationState()
    state.set_target_angle(0.2)
    state.advance()
    assert state.angle == pytest.approx(0.044)
    assert state.pose.angle == pytest.approx(0.044)
    for _ in range(60):
        state.advance()
    assert state.angle == pytest.approx(0.2, abs=1e-6)


def test_speaking_produces_compression_and_bob() -> None:
    state = AnimationState()
    state.set_speaking(True)
    pose = state.advance()
    assert state.phase == pytest.approx(SPEAK_PHASE_STEP)
    pulse = speaking_pulse(SPEAK_PHASE_STEP)
    assert pose.compression == pytest.approx(1.0 - 0.14 * pulse)
    assert pose.bob == pytest.approx(5.0 * pulse)
    assert 0.0 < pose.compression < 1.0
    assert pose.bob > 0.0

    state.set_speaking(False)
    assert state.phase == 0.0
    assert state.pose.compression == pytest.approx(1.0)
    assert state.pose.bob == pytest.approx(0.0)


def test_reduce_motion_freezes_wobble() -> None:
    state = AnimationState(speaking=True, reduce_motion=True)
    state.set_target_angle(0.2)
    pose = state.advance()
    assert pose.angle == pytest.approx(0.2)
    assert pose.compression == pytest.approx(1.0)
    assert pose.bob == pytest.approx(0.0)


def test_window_pose_tracks_speaking_and_tilt(pet: PetWindow) -> None:
    pet.set_tilt(0.2)
    pet.tick()
    assert 0.0 < pet.pose.angle < 0.2
    pet.set_speaking(True)
    pet.tick()
    assert pet.pose.compression < 1.0
    assert pet.pose.bob > 0.0
    pet.set_reduce_motion(True)
    assert pet.pose.compression == pytest.approx(1.0)
    assert pet.pose.bob == pytest.approx(0.0)


def test_speaking_shifts_character_up(pet: PetWindow) -> None:
    flat_bottom = pet.face_rect_global().bottom
    assert pet.pose.bob == pytest.approx(0.0)
    pet.set_speaking(True)
    pet.tick()
    assert pet.pose.bob > 0.0
    assert pet.face_rect_global().bottom < flat_bottom


# --------------------------------------------------------------- 靠近判定


def test_face_rect_global_follows_window_position(pet: PetWindow) -> None:
    pet.move(200, 300)
    assert pet.character_rect() == QRect(PAD_X, TOP, pet.pet_size, pet.pet_size)
    rect = pet.face_rect_global()
    assert rect.x == pytest.approx(200 + PAD_X)
    assert rect.y == pytest.approx(300 + TOP)
    assert rect.width == pytest.approx(pet.pet_size)
    assert rect.height == pytest.approx(pet.pet_size)


def test_face_rect_global_shrinks_while_speaking(pet: PetWindow) -> None:
    flat = pet.face_rect_global()
    pet.set_speaking(True)
    pet.tick()
    squeezed = pet.face_rect_global()
    # 绘制语义：bob 把整个人物上移，压缩以人物底边为锚点，故底边随 bob 上移、顶边额外升高
    assert squeezed.bottom == pytest.approx(flat.bottom - pet.pose.bob)
    assert squeezed.height == pytest.approx(pet.pet_size * pet.pose.compression)
    assert squeezed.height < flat.height
    assert squeezed.width == pytest.approx(flat.width)


# ----------------------------------------------------------------- 字幕


def test_caption_widget_rounds_text_into_bubble(qtbot) -> None:
    bubble = CaptionWidget()
    qtbot.addWidget(bubble)
    bubble.resize(220, BOTTOM_EXTRA)
    assert bubble.bubble_rect().isEmpty()

    bubble.set_caption("你好")
    rect = bubble.bubble_rect()
    assert rect.isValid()
    assert rect.width() <= bubble.width()
    assert rect.width() >= 2 * PADDING
    assert rect.height() >= 2 * PADDING

    longer = CaptionWidget()
    qtbot.addWidget(longer)
    longer.resize(220, BOTTOM_EXTRA)
    longer.set_caption("这是一句比较长的台词，用于验证自动换行是否生效并且不会产生异常")
    assert longer.bubble_rect().height() > rect.height()
    assert longer.bubble_rect().width() <= 220


def test_caption_widget_renders_without_exception(qtbot) -> None:
    bubble = CaptionWidget()
    qtbot.addWidget(bubble)
    bubble.resize(220, BOTTOM_EXTRA)
    bubble.set_caption("测试字幕")
    shot = bubble.grab()
    assert not shot.isNull()
    image = shot.toImage()
    assert any(
        image.pixelColor(x, y).alpha() > 0
        for x in range(0, image.width(), 4)
        for y in range(0, image.height(), 4)
    )
    bubble.close()


def test_window_paint_renders_character_and_caption(pet: PetWindow) -> None:
    pet.set_caption("测试字幕")
    pet.set_tilt(0.2)
    pet.set_speaking(True)
    pet.tick()
    image = QImage(pet.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    pet.render(image)
    painted = sum(
        1
        for x in range(0, image.width(), 4)
        for y in range(0, image.height(), 4)
        if image.pixelColor(x, y).alpha() > 0
    )
    assert painted > 0


def test_window_caption_round_trip(pet: PetWindow) -> None:
    assert pet.caption() == ""
    pet.set_caption("雷：你好")
    assert pet.caption() == "雷：你好"
    pet.set_caption("  ")
    assert pet.caption() == ""


# ------------------------------------------------------- 新增关键帧 / 窗口能力


def test_nod_wave_spin_keyframes() -> None:
    from leiyu_pet.animation import AnimationState, nod_offset, spin_angle, wave_offset

    assert nod_offset(0.0) == 0.0
    assert nod_offset(0.5) == pytest.approx(14.0)
    assert wave_offset(0.0) == pytest.approx(0.0)
    assert wave_offset(1.0) == pytest.approx(0.0)
    assert spin_angle(0.0) == pytest.approx(0.0)
    assert spin_angle(1.0) == pytest.approx(2 * math.pi)

    state = AnimationState()
    state.nod()
    assert state.advance().offset_y < 0  # 向下沉
    state.wave()
    assert state.advance().offset_x > 0
    state.spin()
    assert state.advance().render_angle_degrees > 0
    for _ in range(60):
        state.advance()
    assert state.pose.render_angle_degrees == pytest.approx(360.0)
    assert state.pose.offset_x == pytest.approx(0.0, abs=1e-6)
    assert state.pose.offset_y == pytest.approx(0.0, abs=1e-6)


def test_double_click_emits_role(pet: PetWindow, qtbot) -> None:
    seen: list[str] = []
    pet.double_click.connect(seen.append)
    spot = center_point(pet)
    with qtbot.waitSignal(pet.double_click, timeout=1000):
        send(pet, QEvent.Type.MouseButtonDblClick, spot)
    assert seen == ["lei"]


def test_always_on_top_can_be_toggled(pet: PetWindow) -> None:
    assert pet.always_on_top is True
    pet.set_always_on_top(False)
    assert pet.always_on_top is False
    assert not has_flag(pet.windowFlags(), Qt.WindowType.WindowStaysOnTopHint)
    pet.set_always_on_top(True)
    assert has_flag(pet.windowFlags(), Qt.WindowType.WindowStaysOnTopHint)


def test_hiding_pauses_animation_timer(qtbot) -> None:
    window = PetWindow("lei", animate=True)
    qtbot.addWidget(window)
    window.show()
    assert window._timer.isActive()
    window.hide()
    assert not window._timer.isActive()
    window.show()
    assert window._timer.isActive()
    window.close()


# --------------------------------------------------------------- 火柴人躯体


def test_body_toggle_keeps_the_feet_in_place(qtbot) -> None:
    window = PetWindow("lei", pet_size=220, animate=False)
    qtbot.addWidget(window)
    window.show()
    window.move(100, 120)
    QApplication.processEvents()

    tall = window.height()
    bottom = window.y() + window.height()

    window.set_stick_body_enabled(False)

    assert window.height() < tall
    assert window.y() + window.height() == bottom


def test_torso_is_clickable_but_its_sides_are_not(pet: PetWindow) -> None:
    assert pet.stick_enabled is True
    center_x = pet.width() // 2
    y = int(pet._neck_y() + pet._body_height() * 0.35)

    assert pet.hit_test(QPoint(center_x, y)) is True
    assert pet.hit_test(QPoint(center_x + 60, y)) is False


def test_torso_is_not_clickable_after_disabling_body(pet: PetWindow) -> None:
    y = int(pet._neck_y() + pet._body_height() * 0.35)
    pet.set_stick_body_enabled(False)
    center_x = pet.width() // 2

    assert pet.hit_test(QPoint(center_x, y)) is False


def test_spin_uses_y_flip_with_a_minimum_width(pet: PetWindow) -> None:
    pet.animation.spin()
    # 缓动曲线下 progress≈0.326 对应转满 90°，此时正对侧面。
    pet.animation.spin_progress = 0.3264

    assert abs(pet._spin_flip()) == pytest.approx(0.42)

    pet.set_stick_spin_axis("roll")
    assert pet._spin_flip() == 1.0


def test_alpha_bounds_are_cached_and_normalized(pet: PetWindow) -> None:
    bounds = pet.alpha_bounds
    assert bounds is not None
    assert 0.0 <= bounds[0] < bounds[2] <= 1.0
    assert 0.0 <= bounds[1] < bounds[3] <= 1.0

    pet.update()
    assert pet.alpha_bounds is bounds


def test_actions_are_one_shot_and_ignored_without_body(pet: PetWindow) -> None:
    pet.play_stick_action("wave", 0.4)
    assert pet.stick_state == "wave"

    pet.set_stick_body_enabled(False)
    assert pet.stick_state == "idle"

    pet.play_stick_action("dance", 1.0)
    assert pet.stick_state == "idle"


def test_side_view_uses_the_generated_silhouette(pet: PetWindow) -> None:
    assert pet._side_pixmap is not None
    assert not pet._side_pixmap.isNull()

    pet.animation.spin()
    pet.animation.spin_progress = 0.5  # 背面：cos(pi) = -1，仍然用原图
    assert pet._side_view is False

    pet.animation.spin_progress = 0.3264  # 正对侧面
    assert pet._side_view is True
    assert abs(pet._spin_flip()) == pytest.approx(0.42)


def test_status_badge_is_a_separate_widget(pet: PetWindow) -> None:
    pet.set_caption("台词")
    pet.set_status_text("番茄钟 · 12:34")

    assert pet.caption() == "台词"
    assert pet.status_text() == "番茄钟 · 12:34"
    assert pet.status_widget.isHidden() is False

    pet.set_status_text("")
    assert pet.status_widget.isHidden() is True
    assert pet.caption() == "台词"  # 清状态条不影响台词


# ----------------------------------------------------- 绝对透明与像素级穿透


class _Msg(ctypes.Structure):
    """Win32 MSG 的最小镜像，用来给 nativeEvent 喂 WM_NCHITTEST。"""

    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
        ("lPrivate", wintypes.DWORD),
    ]


def nchittest(window: PetWindow, local: QPoint) -> tuple[bool, int]:
    """按屏幕坐标构造 WM_NCHITTEST 并交给窗口，返回 (handled, result)。"""
    global_point = window.mapToGlobal(local)
    msg = _Msg()
    msg.message = 0x0084  # WM_NCHITTEST
    msg.lParam = ((global_point.y() & 0xFFFF) << 16) | (global_point.x() & 0xFFFF)
    return window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg))


def nchittest_physical(window: PetWindow, screen_x: int, screen_y: int) -> tuple[bool, int]:
    """直接给**物理像素**屏幕坐标（Windows 真正送进来的就是这种值）。"""
    msg = _Msg()
    msg.message = 0x0084  # WM_NCHITTEST
    msg.lParam = ((screen_y & 0xFFFF) << 16) | (screen_x & 0xFFFF)
    return window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg))


def fake_physical_rect(window: PetWindow, scale: float, monkeypatch) -> tuple[int, int, int, int]:
    """假装窗口跑在 ``scale`` 倍缩放的屏幕上：物理矩形比逻辑尺寸大 ``scale`` 倍。"""
    origin = (3000, 2000)
    rect = (
        origin[0],
        origin[1],
        int(origin[0] + window.width() * scale),
        int(origin[1] + window.height() * scale),
    )
    monkeypatch.setattr(pet_window_module, "window_rect", lambda hwnd: rect)
    return rect


def test_window_flags_disable_system_shadow(pet: PetWindow) -> None:
    """无边框透明窗口不能再被系统投影糊上一圈灰边。"""
    assert has_flag(pet.windowFlags(), Qt.WindowType.NoDropShadowWindowHint)
    assert pet.windowType() == Qt.WindowType.Tool


def test_window_paints_nothing_outside_character(pet: PetWindow) -> None:
    image = QImage(pet.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    pet.render(image)
    # 窗口四角与大块空白都必须是全透明（没有任何底板）
    for x, y in ((0, 0), (pet.width() - 1, 0), (0, pet.height() - 1), (5, 5)):
        assert image.pixelColor(x, y).alpha() == 0
    # 人物本体仍然画出来了
    center = center_point(pet)
    assert image.pixelColor(center.x(), center.y()).alpha() > 0


def test_nchittest_passes_through_empty_pixels(pet: PetWindow) -> None:
    handled, result = nchittest(pet, QPoint(4, 4))
    assert handled is True
    assert result == HTTRANSPARENT


def test_nchittest_keeps_events_on_the_head(pet: PetWindow) -> None:
    """命中必须回 HTCLIENT：返回 0（HTNOWHERE）会让整只桌宠点不动、拖不动。"""
    handled, result = nchittest(pet, center_point(pet))
    assert handled is True
    assert result == HTCLIENT


def test_nchittest_keeps_events_on_stick_limbs(pet: PetWindow) -> None:
    """手臂线条上也要能点（旧实现只认躯干中心的一条窄带）。"""
    center_x, neck_y = pet._neck_point()
    pose = pet._stick.pose()
    arm = pose.arms[0]
    unit = pet._body_height()
    mid = QPoint(
        int(center_x + (arm.joint[0] + arm.end[0]) / 2 * unit),
        int(neck_y + (arm.joint[1] + arm.end[1]) / 2 * unit),
    )
    assert pet.hit_test(mid) is True
    handled, result = nchittest(pet, mid)
    assert handled is True
    assert result == HTCLIENT


def test_nchittest_ignores_other_messages(pet: PetWindow) -> None:
    msg = _Msg()
    msg.message = 0x0001  # WM_CREATE
    handled, _result = pet.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg))
    assert handled is False


def test_nchittest_scales_physical_pixels_back_to_logical(pet: PetWindow, monkeypatch) -> None:
    """150% 缩放屏：lParam 是物理像素，当成逻辑坐标用会算出窗口外的坐标。

    这个换算错误会让整只桌宠在任何位置都被判成透明（HTTRANSPARENT），表现就是
    「看得见，却点不到、拖不动、右键也不出菜单」——v2.1.1 起的点不动正根因在此。
    """
    scale = 1.5
    left, top, _right, _bottom = fake_physical_rect(pet, scale, monkeypatch)
    pet.show()

    local = center_point(pet)
    handled, result = nchittest_physical(
        pet, int(left + local.x() * scale), int(top + local.y() * scale)
    )

    assert handled is True
    assert result == HTCLIENT


def test_nchittest_scales_limb_hits_too(pet: PetWindow, monkeypatch) -> None:
    """火柴人线条同样要在高 DPI 下命中，不能只有头部可点。"""
    scale = 1.5
    left, top, _right, _bottom = fake_physical_rect(pet, scale, monkeypatch)
    pet.show()

    center_x, neck_y = pet._neck_point()
    pose = pet._stick.pose()
    arm = pose.arms[0]
    unit = pet._body_height()
    local = QPoint(
        int(center_x + (arm.joint[0] + arm.end[0]) / 2 * unit),
        int(neck_y + (arm.joint[1] + arm.end[1]) / 2 * unit),
    )

    handled, result = nchittest_physical(
        pet, int(left + local.x() * scale), int(top + local.y() * scale)
    )

    assert handled is True
    assert result == HTCLIENT


def test_nchittest_still_passes_through_at_high_dpi(pet: PetWindow, monkeypatch) -> None:
    """换算修好之后，透明像素必须照旧穿透，不能反过来整窗都变实体。"""
    scale = 1.5
    left, top, _right, _bottom = fake_physical_rect(pet, scale, monkeypatch)
    pet.show()

    handled, result = nchittest_physical(pet, int(left + 4 * scale), int(top + 4 * scale))

    assert handled is True
    assert result == HTTRANSPARENT


def test_native_to_local_falls_back_to_device_pixel_ratio(pet: PetWindow, monkeypatch) -> None:
    """拿不到物理矩形时退回 DPR 除法：同样不能把物理像素直接当逻辑坐标。"""
    monkeypatch.setattr(pet_window_module, "window_rect", lambda hwnd: None)
    monkeypatch.setattr(PetWindow, "devicePixelRatioF", lambda self: 2.0)
    origin = pet.mapToGlobal(QPoint(0, 0))

    local = pet._native_to_local(origin.x() * 2 + 24, origin.y() * 2 + 30)

    assert (local.x(), local.y()) == pytest.approx((12.0, 15.0))


def test_window_rect_is_none_without_a_handle() -> None:
    """没有句柄（或不在 Windows 上）时安静返回 None，由调用方回退。"""
    assert platform_win.window_rect(0) is None


def test_hit_test_between_limbs_is_transparent(pet: PetWindow) -> None:
    """两条腿中间的空隙是透明的，点击应该落到底层。"""
    center_x, neck_y = pet._neck_point()
    gap = QPoint(int(center_x), int(neck_y + pet._body_height() * 0.9))
    assert pet.hit_test(gap) is False


def test_click_through_switch_still_wins(pet: PetWindow) -> None:
    pet.set_click_through(True)
    assert pet.hit_test(center_point(pet)) is False
    handled, result = nchittest(pet, center_point(pet))
    assert handled is True
    assert result == HTTRANSPARENT
