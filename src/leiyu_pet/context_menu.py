"""人物右键菜单：复用控制器入口，不复制业务逻辑。"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu

from .models import Role

if TYPE_CHECKING:
    from .runtime import PetRuntime

ROLE_NAMES = {"lei": "雷军", "yu": "余承东"}


class ContextMenuManager(QObject):
    def __init__(self, runtime: PetRuntime) -> None:
        super().__init__(runtime)
        self.runtime = runtime
        self._menus: list[QMenu] = []

    def show(self, role: Role, position: QPoint) -> QMenu:
        window = self.runtime.windows[role]
        menu = QMenu(window)
        self._menus.append(menu)
        menu.aboutToHide.connect(partial(self._release, menu))

        self._add_action(menu, "随机说一段", partial(self.runtime.controller.play_solo, role))
        pair_action = self._add_action(menu, "两人对话一句", self.runtime.controller.start_pair)
        pair_action.setEnabled(self.runtime.controller.update_proximity())

        pick_menu = menu.addMenu("挑一段")
        for clip in self.runtime.pack.clips_for(
            role,
            self.runtime.controller.voice_mode,
            include_explicit=self.runtime.controller.include_explicit,
        ):
            label = clip.text.replace("\n", " ")
            self._add_action(
                pick_menu,
                label[:32] + ("…" if len(label) > 32 else ""),
                partial(self.runtime.controller.play_solo, role, clip.id),
            )

        self._add_action(menu, "停止播放", self.runtime.controller.stop_all)
        menu.addSeparator()
        self._add_voice_menu(menu)
        self._add_volume_menu(menu)
        self._add_distance_menu(menu)
        self._add_size_menu(menu, role)

        tilt_action = self._add_action(
            menu,
            "靠近时互相歪头",
            lambda checked: self.runtime.controller.set_tilt_enabled(checked),
            checkable=True,
            pass_checked=True,
        )
        tilt_action.setChecked(self.runtime.controller.tilt_enabled)

        menu.addSeparator()
        other: Role = "yu" if role == "lei" else "lei"
        other_action = self._add_action(
            menu,
            f"显示{ROLE_NAMES[other]}桌宠",
            partial(self.runtime.toggle_role, other),
            checkable=True,
        )
        other_action.setChecked(self.runtime.windows[other].isVisible())
        self._add_action(menu, "恢复默认位置", partial(self.runtime.reset_position, role))
        self._add_action(menu, "隐藏当前桌宠", partial(self.runtime.set_role_visible, role, False))
        self._add_action(menu, "退出全部", QApplication.instance().quit)
        menu.popup(position)
        return menu

    def _add_voice_menu(self, menu: QMenu) -> None:
        voice_menu = menu.addMenu("声音模式")
        group = QActionGroup(voice_menu)
        group.setExclusive(True)
        for mode, label in (("normal", "原声"), ("helium", "1.5倍氦气版")):
            action = self._add_action(
                voice_menu,
                label,
                partial(self.runtime.controller.set_voice_mode, mode),
                checkable=True,
            )
            action.setChecked(self.runtime.controller.voice_mode == mode)
            group.addAction(action)

    def _add_volume_menu(self, menu: QMenu) -> None:
        volume_menu = menu.addMenu("音量")
        group = QActionGroup(volume_menu)
        group.setExclusive(True)
        for percent in (0, 25, 50, 65, 80, 100):
            action = self._add_action(
                volume_menu,
                f"{percent}%",
                partial(self.runtime.set_volume, percent / 100),
                checkable=True,
            )
            action.setChecked(round(self.runtime.volume * 100) == percent)
            group.addAction(action)

    def _add_distance_menu(self, menu: QMenu) -> None:
        distance_menu = menu.addMenu("歪头距离")
        group = QActionGroup(distance_menu)
        group.setExclusive(True)
        for distance, label in ((8, "贴近"), (32, "靠近"), (80, "较远")):
            action = self._add_action(
                distance_menu,
                f"{label}（{distance}）",
                partial(self.runtime.set_distance, distance),
                checkable=True,
            )
            action.setChecked(round(self.runtime.controller.proximity.distance) == distance)
            group.addAction(action)

    def _add_size_menu(self, menu: QMenu, role: Role) -> None:
        size_menu = menu.addMenu("人物大小")
        group = QActionGroup(size_menu)
        group.setExclusive(True)
        for size, label in ((170, "小"), (220, "中"), (290, "大")):
            action = self._add_action(
                size_menu,
                label,
                partial(self.runtime.set_pet_size, role, size),
                checkable=True,
            )
            action.setChecked(self.runtime.windows[role].pet_size == size)
            group.addAction(action)

    @staticmethod
    def _add_action(
        menu: QMenu,
        text: str,
        callback,
        *,
        checkable: bool = False,
        pass_checked: bool = False,
    ) -> QAction:
        action = menu.addAction(text)
        action.setCheckable(checkable)
        if pass_checked:
            action.triggered.connect(callback)
        else:
            action.triggered.connect(lambda _checked=False, handler=callback: handler())
        return action

    def _release(self, menu: QMenu) -> None:
        try:
            self._menus.remove(menu)
        except ValueError:
            return
        menu.deleteLater()
