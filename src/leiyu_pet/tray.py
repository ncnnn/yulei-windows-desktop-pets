"""系统托盘：单实例全局菜单，复用运行时入口。"""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .autostart import is_enabled, self_check_requested_but_missing, set_enabled
from .config import Config, save_config
from .context_menu import ROLE_NAMES
from .paths import config_path

ROLES = ("lei", "yu")
DISTANCE_VALUES = (8, 32, 80)
DISTANCE_LABELS = {8: "贴近", 32: "靠近", 80: "较远"}
SIZE_VALUES = (170, 220, 290)
SIZE_LABELS = {170: "小", 220: "中", 290: "大"}
VOICE_VALUES = ("normal", "helium")
VOICE_LABELS = {"normal": "原声", "helium": "1.5倍氦气版"}
VOLUMES = (0, 25, 50, 65, 80, 100)


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
        icon = QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_ComputerIcon
        )
        self._tray.setIcon(icon)
        self._tray.setToolTip("雷余双桌宠")

        self._menu = QMenu()
        self._tray.setContextMenu(self._menu)
        self._actions: list[QAction] = []
        self._submenus: list[QMenu] = []

        self._tray.activated.connect(self._on_activated)

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
        self._menu.clear()
        self._build_contents()

    def _add_action(
        self,
        menu: QMenu,
        text: str,
        callback,
        *,
        checkable: bool = False,
        checked: bool = False,
        pass_checked: bool = False,
    ) -> QAction:
        action = menu.addAction(text)
        action.setCheckable(checkable)
        action.setChecked(checked)
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
            )
            group.addAction(action)
        return group

    def _build_contents(self) -> None:
        rt = self.runtime

        self._add_action(
            self._menu,
            f"显示/隐藏{ROLE_NAMES['lei']}桌宠",
            lambda checked=False, role="lei": rt.set_role_visible(role, checked),
            checkable=True,
            pass_checked=True,
            checked=rt.windows["lei"].isVisible(),
        )
        self._add_action(
            self._menu,
            f"显示/隐藏{ROLE_NAMES['yu']}桌宠",
            lambda checked=False, role="yu": rt.set_role_visible(role, checked),
            checkable=True,
            pass_checked=True,
            checked=rt.windows["yu"].isVisible(),
        )
        self._add_action(self._menu, "显示全部", rt.show_all)
        self._menu.addSeparator()

        self._add_action(
            self._menu,
            f"{ROLE_NAMES['lei']}随机说一段",
            lambda: rt.controller.play_solo("lei"),
        )
        self._add_action(
            self._menu,
            f"{ROLE_NAMES['yu']}随机说一段",
            lambda: rt.controller.play_solo("yu"),
        )
        self._add_action(self._menu, "两人对话一句", rt.controller.start_pair)
        self._add_action(self._menu, "停止播放", rt.controller.stop_all)
        self._menu.addSeparator()

        voice_menu = self._menu.addMenu("声音模式")
        self._submenus.append(voice_menu)
        self._add_radio_group(
            voice_menu,
            VOICE_VALUES,
            label_of=lambda mode: VOICE_LABELS[mode],
            is_checked=lambda mode: rt.controller.voice_mode == mode,
            on_trigger=lambda mode: rt.controller.set_voice_mode(mode),
        )

        volume_menu = self._menu.addMenu("音量")
        self._submenus.append(volume_menu)
        self._add_radio_group(
            volume_menu,
            VOLUMES,
            label_of=lambda p: f"{p}%",
            is_checked=lambda p: round(rt.volume * 100) == p,
            on_trigger=lambda p: rt.set_volume(p / 100),
        )

        distance_menu = self._menu.addMenu("歪头距离")
        self._submenus.append(distance_menu)
        self._add_radio_group(
            distance_menu,
            DISTANCE_VALUES,
            label_of=lambda d: f"{DISTANCE_LABELS[d]}（{d}）",
            is_checked=lambda d: round(rt.controller.proximity.distance) == d,
            on_trigger=lambda d: rt.set_distance(d),
        )

        size_menu = self._menu.addMenu("人物大小")
        self._submenus.append(size_menu)
        for role in ROLES:
            role_menu = size_menu.addMenu(ROLE_NAMES[role])
            self._submenus.append(role_menu)
            self._add_radio_group(
                role_menu,
                SIZE_VALUES,
                label_of=lambda s: SIZE_LABELS[s],
                is_checked=lambda s, r=role: rt.windows[r].pet_size == s,
                on_trigger=lambda s, r=role: rt.set_pet_size(r, s),
            )

        self._add_action(
            self._menu,
            "靠近时互相歪头",
            lambda checked=False: rt.controller.set_tilt_enabled(checked),
            checkable=True,
            pass_checked=True,
            checked=rt.controller.tilt_enabled,
        )
        self._menu.addSeparator()

        self._add_action(
            self._menu,
            "开机自启",
            self._toggle_autostart,
            checkable=True,
            pass_checked=True,
            checked=is_enabled() or self.config.autostart,
        )
        if self._on_open_settings is not None:
            self._add_action(self._menu, "设置", self._on_open_settings)

        quit_handler = self._on_quit or (lambda: QApplication.instance().quit())
        self._add_action(self._menu, "退出", quit_handler)

    def _toggle_autostart(self, checked: bool) -> None:
        try:
            set_enabled(checked)
        except Exception:
            self._tray.showMessage(
                "开机自启",
                "设置失败，可能被安全软件拦截",
                QSystemTrayIcon.MessageIcon.Warning,
            )
            checked = False
        self.config.autostart = checked
        save_config(self.config, config_path())

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
