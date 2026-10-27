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
        menu = QMenu(window)
        self._menus.append(menu)
        menu.aboutToHide.connect(partial(self._release, menu))

        self._add_action(menu, "随机说一段", partial(self.runtime.controller.play_solo, role))
        pair_action = self._add_action(menu, "两人对话一句", self.runtime.controller.start_pair)
        pair_action.setEnabled(self.runtime.controller.update_proximity())
        lines = self.runtime.controller.crosstalk_lines
        self._add_action(menu, f"相声模式（一问一答 {lines} 句）", self._start_crosstalk)
        self._add_action(menu, "决战模式（音量 20%→70%）", self._start_battle)

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

        history_menu = menu.addMenu("最近说过")
        entries = self.runtime.controller.recent(role, 6)
        if not entries:
            empty = history_menu.addAction("暂无记录")
            empty.setEnabled(False)
        for clip_id, text in reversed(entries):
            label = text.replace("\n", " ")
            self._add_action(
                history_menu,
                label[:32] + ("…" if len(label) > 32 else ""),
                partial(self.runtime.controller.play_solo, role, clip_id),
            )

        self._add_action(menu, "停止播放", self.runtime.controller.stop_all)
        self._add_action(
            menu,
            "恢复声音" if getattr(self.runtime, "muted", False) else "静音",
            self.runtime.toggle_mute,
        )

        assistant = getattr(self.runtime, "assistant", None)
        if assistant is not None:
            focus_menu = menu.addMenu("番茄钟")
            self._add_action(focus_menu, "开始专注", self._start_pomodoro)
            self._add_action(focus_menu, "停止计时", assistant.stop_pomodoro)
            status = focus_menu.addAction(assistant.pomodoro_status())
            status.setEnabled(False)
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

        wander_action = self._add_action(
            menu,
            "自动游走",
            self.runtime.set_wander_enabled,
            checkable=True,
            pass_checked=True,
        )
        config = getattr(self.runtime, "config", None)
        wander_action.setChecked(bool(getattr(config, "wander_enabled", False)))

        overlap_action = self._add_action(
            menu,
            "重叠时自动互喷",
            self.runtime.set_overlap_easter_egg,
            checkable=True,
            pass_checked=True,
        )
        overlap_action.setChecked(self.runtime.controller.overlap_enabled)

        body_action = self._add_action(
            menu,
            "火柴人躯体",
            self.runtime.set_stick_body_enabled,
            checkable=True,
            pass_checked=True,
        )
        body_action.setChecked(
            bool(getattr(config, "stick_body_enabled", True))
        )

        actions_action = self._add_action(
            menu,
            "随机动作（招手/跳舞）",
            self._toggle_stick_random,
            checkable=True,
            pass_checked=True,
        )
        actions_action.setChecked(
            bool(getattr(config, "stick_random_action_enabled", True))
        )

        frosted_action = self._add_action(
            menu,
            "磨砂菜单与设置",
            self._toggle_frosted,
            checkable=True,
            pass_checked=True,
        )
        frosted_action.setChecked(bool(getattr(config, "frosted_ui_enabled", True)))

        action_menu = menu.addMenu("让 TA 做个动作")
        for state in RANDOM_ACTIONS:
            self._add_action(
                action_menu,
                ACTION_LABELS[state],
                partial(self._play_action, role, state),
            )

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
        open_settings = getattr(self.runtime, "on_open_settings", None)
        if open_settings is not None:
            self._add_action(menu, "设置…", open_settings)
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

    def _toggle_stick_random(self, checked: bool) -> None:
        config = getattr(self.runtime, "config", None)
        if config is not None:
            config.stick_random_action_enabled = bool(checked)
        self.runtime.set_stick_action_settings(
            bool(checked),
            int(getattr(config, "stick_action_interval", 12)),
        )

    def _toggle_frosted(self, checked: bool) -> None:
        """磨砂只作用于菜单与设置；桌宠窗口仍保持绝对透明。"""
        config = getattr(self.runtime, "config", None)
        if config is not None:
            config.frosted_ui_enabled = bool(checked)
        self.runtime.set_frosted_ui(bool(checked))

    def _play_action(self, role: Role, state: str) -> None:
        window = self.runtime.windows[role]
        window.play_stick_action(state, seconds=3.2)

    def _start_pomodoro(self) -> None:
        assistant = getattr(self.runtime, "assistant", None)
        if assistant is not None:
            assistant.start_pomodoro()

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
