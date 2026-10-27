"""人物右键菜单：复用控制器入口，不复制业务逻辑。"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu

from . import frosted_ui
from .models import Role
from .stick_body import ACTION_LABELS, RANDOM_ACTIONS

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
        menu = frosted_ui.FrostedMenu(window)
        self._menus.append(menu)
        menu.aboutToHide.connect(partial(self._release, menu))

        controller = self.runtime.controller
        lines = controller.crosstalk_lines

        self._add_action(menu, "随机说一段", partial(controller.play_solo, role))
        self._add_action(menu, f"相声模式 · {lines} 句", self._start_crosstalk)
        self._add_action(menu, f"决战模式 · {lines} 句", self._start_battle)

        pick_menu = frosted_ui.submenu(menu, "挑一段")
        for clip in self.runtime.pack.clips_for(
            role,
            controller.voice_mode,
            include_explicit=controller.include_explicit,
        ):
            label = clip.text.replace("\n", " ")
            self._add_action(
                pick_menu,
                label[:32] + ("…" if len(label) > 32 else ""),
                partial(controller.play_solo, role, clip.id),
            )

        action_menu = frosted_ui.submenu(menu, "让 TA 做个动作")
        for state in RANDOM_ACTIONS:
            self._add_action(
                action_menu,
                ACTION_LABELS[state],
                partial(self._play_action, role, state),
            )

        assistant = getattr(self.runtime, "assistant", None)
        if assistant is not None:
            focus_menu = frosted_ui.submenu(menu, "番茄钟")
            self._add_action(focus_menu, "开始专注", self._start_pomodoro)
            self._add_action(focus_menu, "停止计时", assistant.stop_pomodoro)
            status = focus_menu.addAction(assistant.pomodoro_status())
            status.setEnabled(False)

        menu.addSeparator()
        self._add_voice_menu(menu)
        self._add_volume_menu(menu)
        mute_action = self._add_action(
            menu,
            "捂嘴（禁言）",
            self.runtime.set_muted,
            checkable=True,
            pass_checked=True,
        )
        mute_action.setChecked(bool(getattr(self.runtime, "muted", False)))

        menu.addSeparator()
        open_settings = getattr(self.runtime, "on_open_settings", None)
        if open_settings is not None:
            self._add_action(menu, "设置…", open_settings)
        self._add_action(menu, "隐藏当前桌宠", partial(self.runtime.set_role_visible, role, False))
        self._add_action(menu, "退出全部", QApplication.instance().quit)
        self._apply_frosted(menu)
        menu.popup(position)
        return menu

    def _apply_frosted(self, menu: QMenu) -> None:
        """给菜单和它的子菜单统一上材质（子菜单是独立窗口，要逐个处理）。"""
        plan = getattr(self.runtime, "frosted_plan", None)
        if plan is None:
            plan = frosted_ui.current_plan(True)
        for submenu in menu.findChildren(QMenu):
            frosted_ui.apply_menu(submenu, plan)
        frosted_ui.apply_menu(menu, plan)

    def _start_crosstalk(self) -> None:
        """隐藏了一只就先把两只都带出来，再开始交替说。"""
        if self.runtime.controller.start_crosstalk():
            return
        self.runtime.show_all()
        self.runtime.controller.start_crosstalk()

    def _start_battle(self) -> None:
        if self.runtime.controller.start_battle():
            return
        self.runtime.show_all()
        self.runtime.controller.start_battle()

    def _play_action(self, role: Role, state: str) -> None:
        window = self.runtime.windows[role]
        window.play_stick_action(state, seconds=3.2)

    def _start_pomodoro(self) -> None:
        assistant = getattr(self.runtime, "assistant", None)
        if assistant is not None:
            assistant.start_pomodoro()

    def _add_voice_menu(self, menu: QMenu) -> None:
        voice_menu = frosted_ui.submenu(menu, "声音模式")
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
        volume_menu = frosted_ui.submenu(menu, "音量")
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
