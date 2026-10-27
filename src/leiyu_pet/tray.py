"""系统托盘：单实例全局菜单，复用运行时入口。"""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from . import APP_NAME, frosted_ui
from .autostart import self_check_requested_but_missing
from .config import Config
from .context_menu import ROLE_NAMES
from .paths import app_icon_path

ROLES = ("lei", "yu")
VOICE_VALUES = ("normal", "helium")
VOICE_LABELS = {"normal": "原声", "helium": "1.5倍氦气版"}
VOLUMES = (0, 25, 50, 65, 80, 100)
#: 托盘悬浮提示里显示的播放模式。
MODE_LABELS = {
    "crosstalk": "相声中",
    "battle": "决战中",
    "pair": "对话中",
    "solo": "播放中",
}


class TrayManager(QObject):
    def __init__(
        self,
        runtime,
        config: Config,
        *,
        on_open_settings=None,
        on_quit=None,
    ) -> None:
        super().__init__()
        self.runtime = runtime
        self.config = config
        self._on_open_settings = on_open_settings
        self._on_quit = on_quit

        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._app_icon())
        self._tray.setToolTip(APP_NAME)

        self._menu = frosted_ui.FrostedMenu()
        self._tray.setContextMenu(self._menu)
        self._actions: list[QAction] = []
        #: (action, 取值回调)：菜单每次弹出前按最新状态刷新勾选，不用整份重建。
        self._checks: list[tuple[QAction, object]] = []
        self._submenus: list[QMenu] = []
        self._menu.aboutToShow.connect(self._sync_checks)

        self._tray.activated.connect(self._on_activated)
        # 播放模式变化时更新悬浮提示（决战/相声中一眼可见）。
        mode_signal = getattr(getattr(runtime, "controller", None), "mode_changed", None)
        if mode_signal is not None:
            mode_signal.connect(self._on_mode_changed)

    @staticmethod
    def _app_icon() -> QIcon:
        """托盘图标用产品图标，不再借用系统的通用电脑图标。

        旧实现固定用 ``SP_ComputerIcon``，改名、换图标都反映不到托盘上，
        看起来就像「图标没更新」。
        """
        path = app_icon_path()
        if path is not None:
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def show(self) -> None:
        self.build_menu()
        self._tray.show()
        if self_check_requested_but_missing(self.config.autostart):
            self._tray.showMessage(
                "开机自启",
                "开机自启项被安全软件清理，请重新设置",
                QSystemTrayIcon.MessageIcon.Warning,
            )

    def build_menu(self) -> None:
        for sub in self._submenus:
            sub.deleteLater()
        self._submenus = []
        self._actions = []
        self._checks = []
        self._menu.clear()
        self._build_contents()
        self._apply_frosted()

    def _sync_checks(self) -> None:
        """菜单弹出前把勾选状态对齐到最新值。

        菜单内容只在 ``show()``/双击时重建，期间用户可能在设置页或右键菜单里
        改了声音模式、音量、显隐——不刷新就会出现「勾还停在旧位置」的错觉。
        """
        for action, getter in self._checks:
            action.setChecked(bool(getter()))

    def _apply_frosted(self) -> None:
        plan = getattr(self.runtime, "frosted_plan", None)
        if plan is None:
            plan = frosted_ui.current_plan(True)
        for submenu in self._menu.findChildren(QMenu):
            frosted_ui.apply_menu(submenu, plan)
        frosted_ui.apply_menu(self._menu, plan)

    def _add_action(
        self,
        menu: QMenu,
        text: str,
        callback,
        *,
        checkable: bool = False,
        checked: bool = False,
        pass_checked: bool = False,
        checked_of=None,
    ) -> QAction:
        action = menu.addAction(text)
        action.setCheckable(checkable)
        action.setChecked(checked)
        if checked_of is not None:
            self._checks.append((action, checked_of))
        if pass_checked:
            action.triggered.connect(callback)
        else:
            action.triggered.connect(
                lambda _checked=False, handler=callback: handler()
            )
        self._actions.append(action)
        return action

    def _add_radio_group(
        self,
        menu: QMenu,
        values,
        label_of,
        is_checked,
        on_trigger,
    ) -> QActionGroup:
        group = QActionGroup(menu)
        group.setExclusive(True)
        for value in values:
            action = self._add_action(
                menu,
                label_of(value),
                lambda _checked=False, v=value, handler=on_trigger: handler(v),
                checkable=True,
                checked=is_checked(value),
                checked_of=lambda v=value: is_checked(v),
            )
            group.addAction(action)
        return group

    def _build_contents(self) -> None:
        """托盘只留高频操作；播放速度、尺寸、提醒等细节都收进设置页。"""
        rt = self.runtime

        for role in ROLES:
            self._add_action(
                self._menu,
                f"显示/隐藏{ROLE_NAMES[role]}桌宠",
                lambda checked=False, r=role: rt.set_role_visible(r, checked),
                checkable=True,
                pass_checked=True,
                checked=rt.windows[role].isVisible(),
                checked_of=lambda r=role: rt.windows[r].isVisible(),
            )
        self._add_action(self._menu, "显示全部", rt.show_all)
        self._menu.addSeparator()

        for role in ROLES:
            self._add_action(
                self._menu,
                f"{ROLE_NAMES[role]}随机说一段",
                lambda _checked=False, r=role: rt.controller.play_solo(r),
            )
        lines = int(rt.controller.crosstalk_lines)
        self._add_action(self._menu, f"相声模式 · {lines} 句", self._start_crosstalk)
        self._add_action(self._menu, f"决战模式 · {lines} 句", self._start_battle)
        self._add_action(self._menu, "停止播放", rt.controller.stop_all)
        self._menu.addSeparator()

        voice_menu = frosted_ui.submenu(self._menu, "声音模式")
        self._submenus.append(voice_menu)
        self._add_radio_group(
            voice_menu,
            VOICE_VALUES,
            label_of=lambda mode: VOICE_LABELS[mode],
            is_checked=lambda mode: rt.controller.voice_mode == mode,
            on_trigger=lambda mode: rt.controller.set_voice_mode(mode),
        )

        volume_menu = frosted_ui.submenu(self._menu, "音量")
        self._submenus.append(volume_menu)
        self._add_radio_group(
            volume_menu,
            VOLUMES,
            label_of=lambda p: f"{p}%",
            is_checked=lambda p: round(rt.volume * 100) == p,
            on_trigger=lambda p: rt.set_volume(p / 100),
        )
        self._add_action(
            self._menu,
            "恢复声音" if getattr(rt, "muted", False) else "静音",
            rt.toggle_mute,
        )

        focus_menu = frosted_ui.submenu(self._menu, "番茄钟")
        self._submenus.append(focus_menu)
        self._add_action(focus_menu, "开始专注", self._start_pomodoro)
        self._add_action(focus_menu, "停止计时", self._stop_pomodoro)
        assistant = getattr(rt, "assistant", None)
        if assistant is not None:
            focus_menu.addSeparator()
            status = focus_menu.addAction(assistant.pomodoro_status())
            status.setEnabled(False)

        self._menu.addSeparator()
        if self._on_open_settings is not None:
            self._add_action(self._menu, "设置", self._on_open_settings)
        quit_handler = self._on_quit or (lambda: QApplication.instance().quit())
        self._add_action(self._menu, "退出", quit_handler)

    def notify(self, title: str, message: str, *, warning: bool = False) -> None:
        """给主程序用的托盘气泡入口（更新提示、异常兜底）。"""
        icon = (
            QSystemTrayIcon.MessageIcon.Warning
            if warning
            else QSystemTrayIcon.MessageIcon.Information
        )
        self._tray.showMessage(title, message, icon)

    def _start_crosstalk(self) -> None:
        """相声模式需要两只都在场，先带出来再开始。"""
        if self.runtime.controller.start_crosstalk():
            return
        self.runtime.show_all()
        self.runtime.controller.start_crosstalk()

    def _start_battle(self) -> None:
        """决战模式和相声同一套问答节奏，只是音量逐句爬升。"""
        if self.runtime.controller.start_battle():
            return
        self.runtime.show_all()
        self.runtime.controller.start_battle()

    def _start_pomodoro(self) -> None:
        assistant = getattr(self.runtime, "assistant", None)
        if assistant is None:
            return
        if not assistant.start_pomodoro():
            self.notify("番茄钟", "已经在计时了")
        else:
            self.notify("番茄钟", f"开始专注 {assistant.pomodoro.focus_minutes} 分钟")

    def _stop_pomodoro(self) -> None:
        assistant = getattr(self.runtime, "assistant", None)
        if assistant is not None:
            assistant.stop_pomodoro()

    def _configure_assistant(self) -> None:
        assistant = getattr(self.runtime, "assistant", None)
        if assistant is None:
            return
        assistant.configure(
            hourly=bool(getattr(self.config, "hourly_chime", False)),
            break_minutes=int(getattr(self.config, "break_reminder_minutes", 0)),
            focus_minutes=int(getattr(self.config, "pomodoro_focus_minutes", 25)),
            rest_minutes=int(getattr(self.config, "pomodoro_break_minutes", 5)),
        )

    def _on_mode_changed(self, mode: str) -> None:
        label = MODE_LABELS.get(mode)
        self._tray.setToolTip(f"{APP_NAME} · {label}" if label else APP_NAME)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            rt = self.runtime
            all_visible = all(rt.windows[role].isVisible() for role in ROLES)
            if all_visible:
                for role in ROLES:
                    rt.set_role_visible(role, False)
            else:
                rt.show_all()
            self.build_menu()
