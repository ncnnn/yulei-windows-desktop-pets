"""把窗口、音频和业务控制器装配成一个双宠运行时。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from PySide6.QtCore import QObject, QPoint, QRect
from PySide6.QtGui import QGuiApplication

from .audio import AudioCoordinator
from .context_menu import ContextMenuManager
from .models import AssetPack, Role
from .pet_controller import PetController
from .pet_window import PetWindow
from .platform_win import keep_window_on_screen


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
        self.controller = PetController(pack, self.windows, self.audio, parent=self)
        self.menu_manager = ContextMenuManager(self)
        #: 由主程序注入：右键菜单「设置…」的入口。
        self.on_open_settings = None
        #: 由主程序注入：用于把尺寸/速度等改动写回配置。
        self.config = None

        for _role, window in self.windows.items():
            window.click.connect(self.controller.handle_click)
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
        self.volume = min(max(float(volume), 0.0), 1.0)
        self.controller.set_volume(self.volume)

    def set_distance(self, distance: float) -> None:
        self.controller.set_distance(distance)

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
        self.controller.stop_all()
        self.controller.timer.stop()
        for window in self.windows.values():
            window.close()
