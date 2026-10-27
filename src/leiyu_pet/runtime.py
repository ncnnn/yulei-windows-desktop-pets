"""把窗口、音频和业务控制器装配成一个双宠运行时。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from PySide6.QtCore import QObject, QPoint, QRect, QTimer
from PySide6.QtGui import QGuiApplication

from .assistant import PetAssistant
from .audio import AudioCoordinator
from .context_menu import ContextMenuManager
from .models import AssetPack, Role
from .pet_controller import PetController
from .pet_window import PetWindow
from .platform_win import keep_window_on_screen
from .wander import PlayArea, clamp_position, next_target


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
        if not self._wander_targets:
            self._wander_step_timer.stop()
        self.controller.update_proximity()

    def set_distance(self, distance: float) -> None:
        self.controller.set_distance(distance)

    def set_overlap_easter_egg(self, enabled: bool) -> None:
        """重叠自动互喷开关：同步控制器并落盘（右键/托盘/设置页共用）。"""
        self.controller.set_overlap_easter_egg(bool(enabled))
        self._persist_setting("overlap_easter_egg", bool(enabled))

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
        """记录两只桌宠当前位置，供下次启动恢复。"""
        return {
            role: [window.x(), window.y()]
            for role, window in self.windows.items()
        }

    def restore_positions(self, positions: Mapping[str, Sequence[int]] | None) -> bool:
        """恢复上次位置；越界或非法值自动夹回可见屏幕。返回是否恢复了任意一只。"""
        if not positions:
            return False
        restored = False
        for role in cast(tuple[Role, Role], ("lei", "yu")):
            raw = positions.get(role)
            if not raw or len(raw) != 2:
                continue
            try:
                x, y = int(raw[0]), int(raw[1])
            except (TypeError, ValueError):
                continue
            window = self.windows[role]
            rect = keep_window_on_screen(QRect(x, y, window.width(), window.height()))
            window.move(rect.x(), rect.y())
            restored = True
        if restored:
            self.controller.update_proximity()
        return restored

    def close(self) -> None:
        self._wander_timer.stop()
        self._wander_step_timer.stop()
        self.assistant.stop_polling()
        self.controller.stop_all()
        self.controller.timer.stop()
        for window in self.windows.values():
            window.close()
