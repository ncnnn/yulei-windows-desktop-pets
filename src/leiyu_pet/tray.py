"""系统托盘：单实例全局菜单，复用运行时入口。"""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .autostart import is_enabled, self_check_requested_but_missing, set_enabled
from .config import Config, save_config
from .context_menu import ROLE_NAMES
from .crosstalk import LINE_PRESETS
from .paths import config_path
from .reminders import BREAK_PRESETS

ROLES = ("lei", "yu")
DISTANCE_VALUES = (8, 32, 80)
DISTANCE_LABELS = {8: "贴近", 32: "靠近", 80: "较远"}
SIZE_VALUES = (170, 220, 290)
SIZE_LABELS = {170: "小", 220: "中", 290: "大"}
VOICE_VALUES = ("normal", "helium")
VOICE_LABELS = {"normal": "原声", "helium": "1.5倍氦气版"}
VOLUMES = (0, 25, 50, 65, 80, 100)
PLAYBACK_RATES = (0.8, 1.0, 1.25)
RATE_LABELS = {0.8: "慢放 0.8×", 1.0: "常速 1.0×", 1.25: "快放 1.25×"}
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
        # 播放模式变化时更新悬浮提示（决战/相声中一眼可见）。
        mode_signal = getattr(getattr(runtime, "controller", None), "mode_changed", None)
        if mode_signal is not None:
            mode_signal.connect(self._on_mode_changed)

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

        history_menu = self._menu.addMenu("最近说过")
        self._submenus.append(history_menu)
        for role in ROLES:
            role_history = history_menu.addMenu(f"{ROLE_NAMES[role]}最近说过")
            self._submenus.append(role_history)
            entries = rt.controller.recent(role, 6)
            if not entries:
                empty = role_history.addAction("暂无记录")
                empty.setEnabled(False)
                continue
            for clip_id, text in reversed(entries):
                label = text.replace("\n", " ")
                self._add_action(
                    role_history,
                    label[:28] + ("…" if len(label) > 28 else ""),
                    lambda _checked=False, r=role, cid=clip_id: rt.controller.play_solo(r, cid),
                )

        crosstalk_menu = self._menu.addMenu("相声模式")
        self._submenus.append(crosstalk_menu)
        self._add_action(crosstalk_menu, "开始（一问一答交替说）", self._start_crosstalk)
        self._add_action(
            crosstalk_menu,
            "决战模式（每句音量 20%→70%）",
            self._start_battle,
        )
        crosstalk_menu.addSeparator()
        self._add_radio_group(
            crosstalk_menu,
            LINE_PRESETS,
            label_of=lambda lines: f"{lines} 句",
            is_checked=lambda lines: int(rt.controller.crosstalk_lines) == lines,
            on_trigger=self._set_crosstalk_lines,
        )

        self._add_action(self._menu, "停止播放", rt.controller.stop_all)
        self._add_action(
            self._menu,
            "恢复声音" if getattr(rt, "muted", False) else "静音",
            rt.toggle_mute,
        )

        focus_menu = self._menu.addMenu("番茄钟")
        self._submenus.append(focus_menu)
        self._add_action(focus_menu, "开始专注", self._start_pomodoro)
        self._add_action(focus_menu, "停止计时", self._stop_pomodoro)
        assistant = getattr(rt, "assistant", None)
        if assistant is not None:
            focus_menu.addSeparator()
            status = focus_menu.addAction(assistant.pomodoro_status())
            status.setEnabled(False)

        reminder_menu = self._menu.addMenu("提醒")
        self._submenus.append(reminder_menu)
        self._add_action(
            reminder_menu,
            "整点报时",
            self._toggle_hourly,
            checkable=True,
            pass_checked=True,
            checked=bool(getattr(self.config, "hourly_chime", False)),
        )
        break_menu = reminder_menu.addMenu("久坐提醒")
        self._submenus.append(break_menu)
        self._add_radio_group(
            break_menu,
            BREAK_PRESETS,
            label_of=lambda minutes: "关闭" if minutes == 0 else f"{minutes} 分钟",
            is_checked=lambda minutes: int(
                getattr(self.config, "break_reminder_minutes", 0)
            )
            == minutes,
            on_trigger=self._set_break_minutes,
        )
        self._add_action(
            reminder_menu,
            "免打扰时段",
            self._toggle_quiet,
            checkable=True,
            pass_checked=True,
            checked=bool(getattr(self.config, "quiet_hours_enabled", False)),
        )
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

        speed_menu = self._menu.addMenu("播放速度")
        self._submenus.append(speed_menu)
        self._add_radio_group(
            speed_menu,
            PLAYBACK_RATES,
            label_of=lambda rate: RATE_LABELS[rate],
            is_checked=lambda rate: abs(rt.controller.playback_rate - rate) < 0.01,
            on_trigger=lambda rate: rt.set_rate(rate),
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
        self._add_action(
            self._menu,
            "自动游走",
            self._toggle_wander,
            checkable=True,
            pass_checked=True,
            checked=bool(getattr(self.config, "wander_enabled", False)),
        )
        self._add_action(
            self._menu,
            "重叠时自动互喷",
            self._toggle_overlap,
            checkable=True,
            pass_checked=True,
            checked=bool(getattr(self.config, "overlap_easter_egg", False)),
        )
        self._add_action(
            self._menu,
            "火柴人躯体",
            self._toggle_stick_body,
            checkable=True,
            pass_checked=True,
            checked=bool(getattr(self.config, "stick_body_enabled", True)),
        )
        self._add_action(
            self._menu,
            "随机动作（招手/跳舞）",
            self._toggle_stick_random,
            checkable=True,
            pass_checked=True,
            checked=bool(getattr(self.config, "stick_random_action_enabled", True)),
        )
        self._add_action(
            self._menu,
            "对话开场决斗特效",
            self._toggle_duel_effect,
            checkable=True,
            pass_checked=True,
            checked=bool(getattr(self.config, "duel_effect_enabled", True)),
        )
        self._add_action(
            self._menu,
            "半透明磨砂面板",
            self._toggle_glass,
            checkable=True,
            pass_checked=True,
            checked=bool(getattr(self.config, "glass_enabled", True)),
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

    def _set_crosstalk_lines(self, lines: int) -> None:
        self.runtime.controller.set_crosstalk_lines(lines)
        self.config.crosstalk_lines = int(lines)
        save_config(self.config, config_path())

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

    def _toggle_hourly(self, checked: bool) -> None:
        self.config.hourly_chime = bool(checked)
        save_config(self.config, config_path())
        self._configure_assistant()

    def _set_break_minutes(self, minutes: int) -> None:
        self.config.break_reminder_minutes = int(minutes)
        save_config(self.config, config_path())
        self._configure_assistant()

    def _toggle_quiet(self, checked: bool) -> None:
        self.config.quiet_hours_enabled = bool(checked)
        save_config(self.config, config_path())

    def _toggle_wander(self, checked: bool) -> None:
        self.config.wander_enabled = bool(checked)
        save_config(self.config, config_path())
        self.runtime.set_wander_enabled(
            bool(checked),
            int(getattr(self.config, "wander_interval_seconds", 45)),
        )

    def _toggle_overlap(self, checked: bool) -> None:
        self.config.overlap_easter_egg = bool(checked)
        save_config(self.config, config_path())
        self.runtime.controller.set_overlap_easter_egg(bool(checked))

    def _toggle_stick_body(self, checked: bool) -> None:
        self.config.stick_body_enabled = bool(checked)
        self.runtime.set_stick_body_enabled(bool(checked))

    def _toggle_duel_effect(self, checked: bool) -> None:
        self.config.duel_effect_enabled = bool(checked)
        self.runtime.set_duel_effect_enabled(bool(checked))

    def _toggle_glass(self, checked: bool) -> None:
        self.config.glass_enabled = bool(checked)
        self.runtime.set_glass(
            bool(checked),
            int(getattr(self.config, "corner_radius", 14)),
        )

    def _toggle_stick_random(self, checked: bool) -> None:
        self.config.stick_random_action_enabled = bool(checked)
        self.runtime.set_stick_action_settings(
            bool(checked),
            int(getattr(self.config, "stick_action_interval", 12)),
        )

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

    def _on_mode_changed(self, mode: str) -> None:
        label = MODE_LABELS.get(mode)
        self._tray.setToolTip(f"雷余双桌宠 · {label}" if label else "雷余双桌宠")

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
