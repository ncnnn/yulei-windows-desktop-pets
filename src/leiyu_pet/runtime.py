"""把窗口、音频和业务控制器装配成一个双宠运行时。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from PySide6.QtCore import QObject, QPoint
from PySide6.QtGui import QGuiApplication

from .audio import AudioCoordinator
from .context_menu import ContextMenuManager
from .models import AssetPack, Role
from .pet_controller import PetController
from .pet_window import PetWindow


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
        self.windows[role].set_pet_size(size)
        self.controller.update_proximity()

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
        for role in cast(tuple[Role, Role], ("lei", "yu")):
            window = self.windows[role]
            if window.pos() == QPoint(0, 0):
                self.reset_position(role)

    def close(self) -> None:
        self.controller.stop_all()
        self.controller.timer.stop()
        for window in self.windows.values():
            window.close()
