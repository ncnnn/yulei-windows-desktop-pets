"""PySide6 桌宠窗口层测试：窗口属性、信号、拖动、动画与字幕。"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

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
    y = int(pet._neck_y() + pet._body_height() * 0.8)

    assert pet.hit_test(QPoint(center_x, y)) is True
    assert pet.hit_test(QPoint(center_x + 60, y)) is False


def test_torso_is_not_clickable_after_disabling_body(pet: PetWindow) -> None:
    pet.set_stick_body_enabled(False)
    center_x = pet.width() // 2
    y = int(pet._neck_y() + pet._body_height() * 0.8)

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


# ------------------------------------------------------------- 半透明面板


def test_glass_panel_is_off_until_runtime_applies_it(pet: PetWindow) -> None:
    assert pet.glass_enabled is False
    assert pet.glass_plan.panel is False
    assert pet.panel_rect().isEmpty()


def test_set_glass_enables_frosted_rounded_panel(pet: PetWindow) -> None:
    pet.set_glass(True, 14)
    assert pet.glass_enabled is True
    assert pet.glass_frosted is True
    assert pet.glass_radius == 14
    assert pet.glass_plan.reason == "ok"


def test_set_glass_keeps_radius_when_frost_degrades(pet: PetWindow) -> None:
    """降级顺序：磨砂先丢，圆角保留。"""
    pet.set_glass(True, 20, compositing=False)
    assert pet.glass_enabled is True
    assert pet.glass_frosted is False
    assert pet.glass_radius == 20

    pet.set_glass(True, 20, remote=True)
    assert pet.glass_frosted is False
    assert pet.glass_radius == 20


def test_set_glass_clamps_radius(pet: PetWindow) -> None:
    pet.set_glass(True, 999)
    assert pet.glass_radius == 28
    pet.set_glass(True, -5)
    assert pet.glass_radius == 0


def test_panel_rect_stays_inside_window_and_covers_feet(pet: PetWindow) -> None:
    pet.set_glass(True, 14)
    rect = pet.panel_rect()
    assert rect.left() >= 0
    assert rect.top() >= 0
    assert rect.right() <= pet.width()
    assert rect.bottom() <= pet.height()
    # 面板要包住头顶、下巴与脚底
    assert rect.top() < TOP
    assert rect.bottom() >= int(pet._content_bottom())
    assert rect.contains(center_point(pet))


def test_panel_grows_with_the_stick_body(pet: PetWindow) -> None:
    pet.set_glass(True, 14)
    with_body = pet.panel_rect()
    pet.set_stick_body_enabled(False)
    without_body = pet.panel_rect()
    assert with_body.height() > without_body.height()


def test_panel_hit_area_is_the_rectangle_not_the_rounded_shape(pet: PetWindow) -> None:
    """拖拽热区按矩形算：圆角外侧的角点依然可点，不留「看得见点不动」的缝。"""
    pet.set_glass(True, 24)
    rect = pet.panel_rect()
    corner = QPoint(rect.left() + 1, rect.top() + 1)
    assert pet.hit_test(corner) is True
    outside = QPoint(rect.left() - 3, rect.top())
    assert pet.hit_test(outside) is False


def test_glass_hits_respect_click_through(pet: PetWindow) -> None:
    pet.set_glass(True, 14)
    pet.set_click_through(True)
    assert pet.hit_test(center_point(pet)) is False


def test_glass_does_not_touch_window_flags(pet: PetWindow) -> None:
    """点击功能与置顶优先：加面板不改窗口标志，也不抢焦点。"""
    before = pet.windowFlags()
    pet.set_glass(True, 14)
    assert pet.windowFlags() == before
    assert has_flag(pet.windowFlags(), Qt.WindowType.WindowStaysOnTopHint)
    assert pet.windowType() == Qt.WindowType.Tool


def test_panel_paints_translucent_surface_with_empty_corners(pet: PetWindow) -> None:
    pet.set_glass(True, 24)
    image = QImage(pet.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    pet.render(image)
    rect = pet.panel_rect()
    edge = image.pixelColor(rect.left() + 1, rect.center().y())
    assert edge.alpha() > 0
    # 面板有颜色但不遮住人物：透明度介于全透明与不透明之间
    assert edge.alpha() < 255
    corner = image.pixelColor(rect.left(), rect.top())
    assert corner.alpha() < 60
