"""把窗口、音频和业务控制器装配成一个双宠运行时。"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Mapping, Sequence
from typing import cast

from PySide6.QtCore import QObject, QPoint, QRect, QTimer
from PySide6.QtGui import QGuiApplication

from . import frosted_ui
from .assistant import PetAssistant
from .audio import AudioCoordinator
from .auto_dialog import (
    clamp_chance,
    resolve_mode,
    should_start_dialog,
)
from .context_menu import ContextMenuManager
from .duel_effect import DuelEffect
from .frosted import MENU_RADIUS
from .layout import to_top_left
from .models import AssetPack, Role
from .pet_controller import PetController
from .pet_window import PetWindow
from .platform_win import keep_window_on_screen
from .stick_body import RANDOM_ACTIONS
from .wander import PlayArea, clamp_position, next_target

#: 决斗特效的触发门槛：歪头超过该角度、或正在拖动时不出现。
DUEL_TILT_THRESHOLD_DEGREES = 5.0
#: 刚弹过提醒（番茄钟等）的这段时间内丢弃决斗特效，避免两个动效打架。
DUEL_NOTICE_QUIET_SECONDS = 2.0
#: 自动移动触发对话的最小间隔，避免刚聊完又聊。
AUTO_DIALOG_COOLDOWN_SECONDS = 45.0

logger = logging.getLogger(__name__)


class PetRuntime(QObject):
    def __init__(
        self,
        pack: AssetPack,
        *,
        windows: Mapping[Role, PetWindow] | None = None,
        audio: QObject | None = None,
        show: bool = True,
    ) -> None:
        super().__init__()
        self.pack = pack
        self.windows = dict(windows or self._create_windows())
        self.audio = audio or AudioCoordinator(parent=self)
        self.volume = 0.65
        self.audio.set_volume(self.volume)
        self._volume_before_mute = self.volume
        self.controller = PetController(pack, self.windows, self.audio, parent=self)
        self.menu_manager = ContextMenuManager(self)
        #: 整点/久坐/番茄钟的统一入口。
        self.assistant = PetAssistant(parent=self)
        self.assistant.countdown.connect(self._on_countdown)
        #: 由主程序注入：右键菜单「设置…」的入口。
        self.on_open_settings = None
        #: 由主程序注入：用于把尺寸/速度等改动写回配置。
        self.config = None

        # 自动游走：先按间隔挑落点，再用 30ms 小步移动过去。
        self._wander_interval_seconds = 45
        self._wander_targets: dict[Role, QPoint] = {}
        self._wander_timer = QTimer(self)
        self._wander_timer.timeout.connect(self._plan_wander)
        self._wander_step_timer = QTimer(self)
        self._wander_step_timer.setInterval(30)
        self._wander_step_timer.timeout.connect(self._advance_wander)

        # 火柴人随机动作：每隔一段时间招手或跳舞，连续动作有间隔。
        self._stick_actions_enabled = True
        self._stick_action_interval = 12
        self._stick_action_timer = QTimer(self)
        self._stick_action_timer.timeout.connect(self._maybe_stick_action)

        # 自动移动后按概率发起对话 + 对话开场的决斗特效。
        self._auto_dialog_chance = 0
        self._auto_dialog_mode = "crosstalk"
        self._last_auto_dialog_at = 0.0
        self._last_notice_at = 0.0
        self._duel_enabled = True
        self._duel: DuelEffect | None = None
        # 磨砂 UI：只影响菜单与设置窗口，桌面宠物窗口始终绝对透明。
        self._frosted_enabled = True
        self.controller.conversation_started.connect(self._on_conversation_started)
        self.assistant.notice.connect(self._stamp_notice)

        for _role, window in self.windows.items():
            window.click.connect(self.controller.handle_click)
            window.double_click.connect(self.controller.handle_double_click)
            window.context.connect(self._show_context)
            if show:
                window.show()
        self.reset_positions_if_needed()

    def _create_windows(self) -> dict[Role, PetWindow]:
        windows: dict[Role, PetWindow] = {}
        for role in cast(tuple[Role, Role], ("lei", "yu")):
            window = PetWindow(role)
            if not window.load_image(self.pack.image_path(role)):
                raise RuntimeError(f"无法加载人物图片：{self.pack.image_path(role)}")
            windows[role] = window
        return windows

    def _show_context(self, role: str, position: QPoint) -> None:
        self.menu_manager.show(cast(Role, role), position)

    def set_volume(self, volume: float) -> None:
        next_volume = min(max(float(volume), 0.0), 1.0)
        if next_volume > 0.001:
            self._volume_before_mute = next_volume
        self.volume = next_volume
        self.controller.set_volume(self.volume)

    def toggle_mute(self) -> bool:
        """静音/恢复。返回切换后是否处于静音。"""
        if self.volume > 0.001:
            self._volume_before_mute = self.volume
            self.set_volume(0.0)
        else:
            self.set_volume(self._volume_before_mute or 0.65)
        self._persist_setting("volume", self.volume)
        return self.volume <= 0.001

    @property
    def muted(self) -> bool:
        return self.volume <= 0.001

    def set_opacity(self, value: float) -> None:
        opacity = min(max(float(value), 0.3), 1.0)
        for window in self.windows.values():
            window.set_opacity(opacity)
        self._persist_setting("opacity", opacity)

    def set_caption_font_size(self, value: int) -> None:
        size = min(max(int(value), 9), 20)
        for window in self.windows.values():
            widget = getattr(window, "caption_widget", None)
            if widget is not None:
                widget.set_font_size(size)
        self._persist_setting("caption_font_size", size)

    def set_always_on_top(self, value: bool) -> None:
        for window in self.windows.values():
            window.set_always_on_top(bool(value))
        self._persist_setting("always_on_top", bool(value))

    # ------------------------------------------------------------ 磨砂 UI

    def set_frosted_ui(self, enabled: bool) -> None:
        """右键/托盘菜单与设置窗口的磨砂开关。

        只改 UI 材质，绝不碰桌宠窗口——主窗口必须保持绝对透明（见
        ``PetWindow.nativeEvent`` 的像素级穿透）。
        """
        self._frosted_enabled = bool(enabled)
        self._persist_setting("frosted_ui_enabled", self._frosted_enabled)
        plan = self.frosted_plan
        if plan.reason != "ok":
            logger.info("磨砂 UI 降级：%s", plan.describe())

    @property
    def frosted_enabled(self) -> bool:
        return self._frosted_enabled

    @property
    def frosted_plan(self):
        """当前菜单要用的材质计划（每次现算，系统能力变化也能跟上）。"""
        return frosted_ui.current_plan(self._frosted_enabled, MENU_RADIUS)

    def set_wander_enabled(self, enabled: bool, interval_seconds: int | None = None) -> None:
        if interval_seconds is not None:
            self._wander_interval_seconds = min(max(int(interval_seconds), 10), 600)
        self._persist_setting("wander_enabled", bool(enabled))
        self._persist_setting("wander_interval_seconds", self._wander_interval_seconds)
        if enabled:
            self._wander_timer.start(self._wander_interval_seconds * 1000)
        else:
            self._wander_timer.stop()
            self._wander_targets.clear()
            self._wander_step_timer.stop()

    def _play_area(self) -> PlayArea | None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        area = screen.availableGeometry()
        return PlayArea(area.x(), area.y(), area.width(), area.height())

    def _plan_wander(self) -> None:
        """给每只可见、未被拖动的桌宠挑一个新落点。"""
        if self._wander_targets or self.controller.is_busy():
            return
        area = self._play_area()
        if area is None:
            return
        for role, window in self.windows.items():
            if not window.isVisible() or getattr(window, "dragging", False):
                continue
            if getattr(window, "locked", False):
                continue
            target = next_target(
                (window.x(), window.y()),
                window.width(),
                window.height(),
                area,
            )
            self._wander_targets[role] = QPoint(*target)
        if self._wander_targets:
            self._wander_step_timer.start()

    def _advance_wander(self) -> None:
        """按剩余距离的比例小步靠近目标，到点即移除。"""
        if not self._wander_targets:
            self._wander_step_timer.stop()
            return
        area = self._play_area()
        for role in list(self._wander_targets):
            window = self.windows[role]
            target = self._wander_targets[role]
            if not window.isVisible() or getattr(window, "dragging", False):
                self._wander_targets.pop(role, None)
                continue
            dx = target.x() - window.x()
            dy = target.y() - window.y()
            if abs(dx) <= 2 and abs(dy) <= 2:
                self._wander_targets.pop(role, None)
                continue
            step_x = window.x() + int(dx * 0.08) + (1 if dx > 0 else -1 if dx < 0 else 0)
            step_y = window.y() + int(dy * 0.08) + (1 if dy > 0 else -1 if dy < 0 else 0)
            if area is not None:
                step_x, step_y = clamp_position(
                    step_x, step_y, window.width(), window.height(), area
                )
            window.move(step_x, step_y)
        finished = False
        if not self._wander_targets:
            self._wander_step_timer.stop()
            finished = True
        self.controller.update_proximity()
        if finished:
            self._maybe_auto_dialog()

    # ------------------------------------------------------- 自动对话与决斗

    def set_auto_dialog(self, chance: int, mode: str) -> None:
        """自动移动结束后发起对话的概率与模式（0 表示关闭）。"""
        self._auto_dialog_chance = clamp_chance(chance)
        self._auto_dialog_mode = (
            mode if mode in {"crosstalk", "battle", "random"} else "crosstalk"
        )
        self._persist_setting("auto_move_dialog_chance", self._auto_dialog_chance)
        self._persist_setting("auto_move_dialog_mode", self._auto_dialog_mode)

    def set_duel_effect_enabled(self, enabled: bool) -> None:
        """决斗特效开关（纯视觉，与决战模式的音量阶梯无关）。"""
        self._duel_enabled = bool(enabled)
        self._persist_setting("duel_effect_enabled", self._duel_enabled)
        if not self._duel_enabled and self._duel is not None:
            self._duel.stop()

    def _stamp_notice(self, _message: str) -> None:
        self._last_notice_at = time.monotonic()

    def _on_conversation_started(self, mode: str) -> None:
        self._play_duel_effect(mode)

    def _duel_center(self) -> QPoint | None:
        if not self.controller.both_visible():
            return None
        lei = self.windows["lei"].face_rect_global()
        yu = self.windows["yu"].face_rect_global()
        return QPoint(
            int((lei.center_x + yu.center_x) / 2),
            int((lei.y + lei.height / 2 + yu.y + yu.height / 2) / 2),
        )

    def _play_duel_effect(self, reason: str) -> bool:
        """每场对话开场出一次；同一时刻只允许一个，后来的丢弃并记日志。"""
        if not self._duel_enabled:
            return False
        if time.monotonic() - self._last_notice_at < DUEL_NOTICE_QUIET_SECONDS:
            logger.info("决斗特效丢弃：刚弹过提醒（%s）", reason)
            return False
        if any(getattr(window, "dragging", False) for window in self.windows.values()):
            logger.info("决斗特效丢弃：正在拖动（%s）", reason)
            return False
        for role, window in self.windows.items():
            angle = abs(float(getattr(getattr(window, "pose", None), "angle_degrees", 0.0)))
            if angle > DUEL_TILT_THRESHOLD_DEGREES:
                logger.info("决斗特效丢弃：%s 歪头 %.1f°（%s）", role, angle, reason)
                return False
        center = self._duel_center()
        if center is None:
            return False
        if self._duel is None:
            self._duel = DuelEffect(self._duel_center)
        if not self._duel.play_at(center):
            logger.info("决斗特效丢弃：上一个还没播完（%s）", reason)
            return False
        logger.info("决斗特效播放（%s）@ (%d,%d)", reason, center.x(), center.y())
        return True

    def _maybe_auto_dialog(self) -> None:
        """自动移动停稳后，按配置概率发起一段对话。"""
        if not self.controller.both_visible() or self.controller.is_busy():
            return
        if not should_start_dialog(self._auto_dialog_chance, random.random()):
            return
        if time.monotonic() - self._last_auto_dialog_at < AUTO_DIALOG_COOLDOWN_SECONDS:
            return
        mode = resolve_mode(self._auto_dialog_mode)
        started = (
            self.controller.start_battle()
            if mode == "battle"
            else self.controller.start_crosstalk()
        )
        if started:
            self._last_auto_dialog_at = time.monotonic()
            logger.info("自动移动后触发对话：%s", mode)

    def set_distance(self, distance: float) -> None:
        self.controller.set_distance(distance)

    def set_overlap_easter_egg(self, enabled: bool) -> None:
        """重叠自动互喷开关：同步控制器并落盘（右键/托盘/设置页共用）。"""
        self.controller.set_overlap_easter_egg(bool(enabled))
        self._persist_setting("overlap_easter_egg", bool(enabled))

    # ------------------------------------------------------------ 火柴人

    def set_stick_body_enabled(self, enabled: bool) -> None:
        """火柴人躯体总开关；关闭后回到只有大头，窗口回缩但脚不动。"""
        for window in self.windows.values():
            window.set_stick_body_enabled(bool(enabled))
        self.controller.update_proximity()
        self._persist_setting("stick_body_enabled", bool(enabled))
        self._schedule_stick_actions()

    def set_stick_action_settings(self, enabled: bool, interval_seconds: int) -> None:
        self._stick_actions_enabled = bool(enabled)
        raw = int(interval_seconds)
        self._stick_action_interval = 0 if raw <= 0 else max(8, raw)
        self._persist_setting("stick_random_action_enabled", self._stick_actions_enabled)
        self._persist_setting("stick_action_interval", self._stick_action_interval)
        self._schedule_stick_actions()

    def _schedule_stick_actions(self) -> None:
        any_body = any(
            getattr(window, "stick_enabled", False) for window in self.windows.values()
        )
        if self._stick_actions_enabled and self._stick_action_interval > 0 and any_body:
            self._stick_action_timer.start(self._stick_action_interval * 1000)
        else:
            self._stick_action_timer.stop()

    def _maybe_stick_action(self) -> None:
        """随机动作：只在空闲、可见、未被拖动时挑一只做个动作。"""
        if self.controller.is_busy():
            return
        candidates = [
            window
            for window in self.windows.values()
            if window.isVisible()
            and getattr(window, "stick_enabled", False)
            and not getattr(window, "dragging", False)
        ]
        if not candidates:
            return
        window = random.choice(candidates)
        window.play_stick_action(
            random.choice(RANDOM_ACTIONS), seconds=random.uniform(2.4, 3.6)
        )

    def _on_countdown(self, text: str) -> None:
        """番茄钟每秒刷新常驻气泡；正在说话时由控制器自动让位、说完补上。"""
        if not text:
            self.controller.clear_status()
            return
        role: Role = "lei" if self.windows["lei"].isVisible() else "yu"
        self.controller.set_status(role, f"番茄钟 · {text}")

    def set_pet_size(self, role: Role, size: int) -> None:
        """调整人物大小，并立即写回配置（重启后不再丢失）。"""
        self.windows[role].set_pet_size(size)
        self.controller.update_proximity()
        self._persist_setting(f"{role}_size", int(size))

    def set_rate(self, rate: float) -> None:
        self.controller.set_rate(rate)
        self._persist_setting("playback_rate", self.controller.playback_rate)

    def _persist_setting(self, key: str, value) -> None:
        config = self.config
        if config is None or getattr(config, key, None) == value:
            return
        setattr(config, key, value)
        from .config import save_config
        from .paths import config_path

        try:
            save_config(config, config_path())
        except OSError:
            pass

    def set_role_visible(self, role: Role, visible: bool) -> None:
        self.windows[role].setVisible(bool(visible))
        self.controller.update_proximity()

    def toggle_role(self, role: Role) -> None:
        self.set_role_visible(role, not self.windows[role].isVisible())

    def show_all(self) -> None:
        for role in cast(tuple[Role, Role], ("lei", "yu")):
            self.set_role_visible(role, True)
            self.windows[role].raise_()

    def reset_position(self, role: Role) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        window = self.windows[role]
        x = area.left() + (24 if role == "lei" else 440)
        y = area.bottom() - window.height() - 24
        window.move(x, y)
        self.controller.update_proximity()

    def reset_positions_if_needed(self) -> None:
        """启动时确保两只不会重叠，否则会被误判为「靠近」而改变点击行为。"""
        lei = self.windows["lei"].pos()
        yu = self.windows["yu"].pos()
        if lei == QPoint(0, 0) or yu == QPoint(0, 0) or lei == yu:
            for role in cast(tuple[Role, Role], ("lei", "yu")):
                self.reset_position(role)

    def capture_positions(self) -> dict[str, list[int]]:
        """记录两只桌宠的**底边中点**，下次启动按同一锚点还原。"""
        return {
            role: [window.x() + window.width() // 2, window.y() + window.height()]
            for role, window in self.windows.items()
        }

    def restore_positions(self, positions: Mapping[str, Sequence[int]] | None) -> bool:
        """恢复上次位置（底边中点）；越界或非法值自动夹回可见屏幕。"""
        if not positions:
            return False
        restored = False
        for role in cast(tuple[Role, Role], ("lei", "yu")):
            raw = positions.get(role)
            if not raw or len(raw) != 2:
                continue
            try:
                center_x, center_y = int(raw[0]), int(raw[1])
            except (TypeError, ValueError):
                continue
            window = self.windows[role]
            x, y = to_top_left(center_x, center_y, window.width(), window.height())
            rect = keep_window_on_screen(QRect(x, y, window.width(), window.height()))
            window.move(rect.x(), rect.y())
            restored = True
        if restored:
            self.controller.update_proximity()
        return restored

    def close(self) -> None:
        self._wander_timer.stop()
        self._wander_step_timer.stop()
        self._stick_action_timer.stop()
        self.assistant.stop_polling()
        self.controller.stop_all()
        self.controller.timer.stop()
        if self._duel is not None:
            self._duel.stop()
            self._duel.close()
            self._duel = None
        for window in self.windows.values():
            window.close()
