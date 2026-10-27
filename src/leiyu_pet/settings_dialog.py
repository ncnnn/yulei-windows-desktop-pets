"""设置中心：分页（声音 / 互动 / 系统 / 关于），控件改动即时生效并落盘。

安装版与便携版共用同一套代码，所以两边的设置项完全一致；差异只体现在
「关于」页显示的数据目录（``%LOCALAPPDATA%`` 还是 exe 同级 ``data``）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSlider,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from . import __version__, paths
from .auto_dialog import CHANCE_LABELS, DIALOG_CHANCES, DIALOG_MODES, MODE_LABELS
from .autostart import is_enabled, set_enabled
from .config import Config, save_config
from .context_menu import ROLE_NAMES
from .crosstalk import LINE_PRESETS
from .hotkeys import ACTION_LABELS, DEFAULT_BINDINGS, describe_binding
from .pomodoro import BREAK_PRESETS as POMODORO_BREAKS
from .pomodoro import FOCUS_PRESETS
from .reminders import BREAK_PRESETS

ROLES = ("lei", "yu")
DISTANCES = ((8, "贴近"), (32, "靠近"), (80, "较远"))
SIZES = ((170, "小"), (220, "中"), (290, "大"))

COPYRIGHT_NOTICE = (
    "本项目的代码以 MIT 许可发布。\n"
    "音频、头像等素材不在 MIT 许可范围内，版权归原权利人所有。\n"
    "本项目仅用于学习交流与玩梗，不用于商业用途。\n"
    "权利人如认为使用不当，可在仓库开 issue，我们会及时移除。\n"
    "玩法与素材来源致谢：yuhanfu513-ops/leiyu-desktop-pets。"
)


class SettingsDialog(QDialog):
    def __init__(self, runtime, config: Config) -> None:
        super().__init__()
        self.runtime = runtime
        self.config = config
        self.setWindowTitle(f"雷余双桌宠设置 — v{__version__}")
        self.setMinimumWidth(420)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_sound_tab(), "声音")
        self._tabs.addTab(self._build_interaction_tab(), "互动")
        self._tabs.addTab(self._build_appearance_tab(), "外观")
        self._tabs.addTab(self._build_system_tab(), "系统")
        self._tabs.addTab(self._build_about_tab(), "关于")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs)
        layout.addWidget(buttons)

    # ---------------------------------------------------------------- 声音
    def _build_sound_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("volume")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(round(self.runtime.volume * 100))
        self.volume_slider.valueChanged.connect(self._on_volume)
        form.addRow("音量", self.volume_slider)

        self.volume_hint = QLabel("")
        self.volume_hint.setObjectName("volume_hint")
        self.volume_hint.setWordWrap(True)
        form.addRow(self.volume_hint)
        self._refresh_volume_hint(round(self.runtime.volume * 100))

        self.voice_combo = QComboBox()
        self.voice_combo.setObjectName("voice")
        self.voice_combo.addItem("原声", "normal")
        self.voice_combo.addItem("1.5 倍氦气版", "helium")
        self.voice_combo.setCurrentIndex(
            max(self.voice_combo.findData(self.runtime.controller.voice_mode), 0)
        )
        self.voice_combo.currentIndexChanged.connect(
            lambda index: self._set_voice(self.voice_combo.itemData(index))
        )
        form.addRow("声音模式", self.voice_combo)

        self.rate_combo = QComboBox()
        self.rate_combo.setObjectName("playback_rate")
        for rate, label in ((0.8, "慢放 0.8×"), (1.0, "常速 1.0×"), (1.25, "快放 1.25×")):
            self.rate_combo.addItem(label, rate)
        current_rate = float(self.runtime.controller.playback_rate)
        rate_index = self.rate_combo.findData(current_rate)
        if rate_index < 0:
            self.rate_combo.addItem(f"{current_rate:g}×", current_rate)
            rate_index = self.rate_combo.count() - 1
        self.rate_combo.setCurrentIndex(rate_index)
        self.rate_combo.currentIndexChanged.connect(self._on_rate)
        form.addRow("播放速度", self.rate_combo)

        self.caption_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.caption_size_slider.setObjectName("caption_font_size")
        self.caption_size_slider.setRange(9, 20)
        self.caption_size_slider.setValue(int(getattr(self.config, "caption_font_size", 11)))
        self.caption_size_slider.valueChanged.connect(self._on_caption_size)
        form.addRow("字幕字号", self.caption_size_slider)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setObjectName("opacity")
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(
            round(float(getattr(self.config, "opacity", 1.0)) * 100)
        )
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        form.addRow("窗口透明度", self.opacity_slider)

        self.explicit_check = QCheckBox("允许第 17 段（含粗口）")
        self.explicit_check.setObjectName("explicit")
        self.explicit_check.setChecked(self.runtime.controller.include_explicit)
        self.explicit_check.toggled.connect(self._on_explicit)
        form.addRow(self.explicit_check)
        return page

    # ---------------------------------------------------------------- 互动
    def _build_interaction_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.tilt_check = QCheckBox("靠近时互相歪头")
        self.tilt_check.setObjectName("tilt")
        self.tilt_check.setChecked(self.runtime.controller.tilt_enabled)
        self.tilt_check.toggled.connect(self._on_tilt)
        form.addRow(self.tilt_check)

        self.distance_combo = QComboBox()
        self.distance_combo.setObjectName("distance")
        for value, label in DISTANCES:
            self.distance_combo.addItem(f"{label}（{value}）", value)
        current = round(self.runtime.controller.proximity.distance)
        self.distance_combo.setCurrentIndex(max(self.distance_combo.findData(current), 0))
        self.distance_combo.currentIndexChanged.connect(
            lambda index: self.runtime.set_distance(self.distance_combo.itemData(index))
        )
        form.addRow("歪头距离", self.distance_combo)

        self.size_combos: dict[str, QComboBox] = {}
        for role in ROLES:
            combo = QComboBox()
            combo.setObjectName(f"size_{role}")
            for value, label in SIZES:
                combo.addItem(label, value)
            combo.setCurrentIndex(max(combo.findData(self.runtime.windows[role].pet_size), 1))
            combo.currentIndexChanged.connect(
                lambda index, r=role, box=combo: self.runtime.set_pet_size(r, box.itemData(index))
            )
            self.size_combos[role] = combo
            form.addRow(f"{ROLE_NAMES[role]}大小", combo)

        self.crosstalk_combo = QComboBox()
        self.crosstalk_combo.setObjectName("crosstalk_lines")
        for lines in LINE_PRESETS:
            self.crosstalk_combo.addItem(f"{lines} 句", lines)
        current_lines = int(self.runtime.controller.crosstalk_lines)
        if self.crosstalk_combo.findData(current_lines) < 0:
            self.crosstalk_combo.addItem(f"{current_lines} 句", current_lines)
        self.crosstalk_combo.setCurrentIndex(
            max(self.crosstalk_combo.findData(current_lines), 0)
        )
        self.crosstalk_combo.currentIndexChanged.connect(self._on_crosstalk_lines)
        form.addRow("相声模式句数", self.crosstalk_combo)

        self.reduce_motion_check = QCheckBox("减少动效（降低弹动与歪头幅度）")
        self.reduce_motion_check.setObjectName("reduce_motion")
        self.reduce_motion_check.setChecked(self.config.reduce_motion)
        self.reduce_motion_check.toggled.connect(self._on_reduce_motion)
        form.addRow(self.reduce_motion_check)

        self.wander_check = QCheckBox("空闲时自动在屏幕上溜达")
        self.wander_check.setObjectName("wander")
        self.wander_check.setChecked(bool(getattr(self.config, "wander_enabled", False)))
        self.wander_check.toggled.connect(self._on_wander)
        form.addRow(self.wander_check)

        self.wander_interval_combo = QComboBox()
        self.wander_interval_combo.setObjectName("wander_interval")
        for seconds, label in ((30, "30 秒"), (45, "45 秒"), (90, "90 秒"), (180, "3 分钟")):
            self.wander_interval_combo.addItem(label, seconds)
        current_interval = int(getattr(self.config, "wander_interval_seconds", 45))
        self.wander_interval_combo.setCurrentIndex(
            max(self.wander_interval_combo.findData(current_interval), 0)
        )
        self.wander_interval_combo.currentIndexChanged.connect(self._on_wander_interval)
        form.addRow("游走间隔", self.wander_interval_combo)

        self.overlap_check = QCheckBox("两只叠在一起时自动来一段问答")
        self.overlap_check.setObjectName("overlap")
        self.overlap_check.setChecked(
            bool(getattr(self.config, "overlap_easter_egg", False))
        )
        self.overlap_check.toggled.connect(self._on_overlap)
        form.addRow(self.overlap_check)

        self.auto_dialog_combo = QComboBox()
        self.auto_dialog_combo.setObjectName("auto_dialog_chance")
        for percent in DIALOG_CHANCES:
            self.auto_dialog_combo.addItem(CHANCE_LABELS[percent], percent)
        current_chance = int(getattr(self.config, "auto_move_dialog_chance", 0))
        self.auto_dialog_combo.setCurrentIndex(
            max(self.auto_dialog_combo.findData(current_chance), 0)
        )
        self.auto_dialog_combo.currentIndexChanged.connect(self._on_auto_dialog_chance)
        form.addRow("自动移动后对话", self.auto_dialog_combo)

        self.auto_dialog_mode_combo = QComboBox()
        self.auto_dialog_mode_combo.setObjectName("auto_dialog_mode")
        for mode in DIALOG_MODES:
            self.auto_dialog_mode_combo.addItem(MODE_LABELS[mode], mode)
        current_mode = str(getattr(self.config, "auto_move_dialog_mode", "crosstalk"))
        self.auto_dialog_mode_combo.setCurrentIndex(
            max(self.auto_dialog_mode_combo.findData(current_mode), 0)
        )
        self.auto_dialog_mode_combo.currentIndexChanged.connect(self._on_auto_dialog_mode)
        form.addRow("对话模式", self.auto_dialog_mode_combo)

        self.duel_check = QCheckBox("对话开场播放决斗特效（VS，约 1 秒）")
        self.duel_check.setObjectName("duel_effect")
        self.duel_check.setChecked(bool(getattr(self.config, "duel_effect_enabled", True)))
        self.duel_check.toggled.connect(self._on_duel_effect)
        form.addRow(self.duel_check)

        self.hourly_check = QCheckBox("整点报时（静音气泡，不发声）")
        self.hourly_check.setObjectName("hourly_chime")
        self.hourly_check.setChecked(bool(getattr(self.config, "hourly_chime", False)))
        self.hourly_check.toggled.connect(self._on_hourly)
        form.addRow(self.hourly_check)

        self.break_reminder_combo = QComboBox()
        self.break_reminder_combo.setObjectName("break_reminder")
        for minutes in BREAK_PRESETS:
            label = "关闭" if minutes == 0 else f"{minutes} 分钟"
            self.break_reminder_combo.addItem(label, minutes)
        current_break = int(getattr(self.config, "break_reminder_minutes", 0))
        self.break_reminder_combo.setCurrentIndex(
            max(self.break_reminder_combo.findData(current_break), 0)
        )
        self.break_reminder_combo.currentIndexChanged.connect(self._on_break_reminder)
        form.addRow("久坐提醒", self.break_reminder_combo)

        self.focus_combo = QComboBox()
        self.focus_combo.setObjectName("pomodoro_focus")
        for minutes in FOCUS_PRESETS:
            self.focus_combo.addItem(f"{minutes} 分钟", minutes)
        current_focus = int(getattr(self.config, "pomodoro_focus_minutes", 25))
        self.focus_combo.setCurrentIndex(max(self.focus_combo.findData(current_focus), 0))
        self.focus_combo.currentIndexChanged.connect(self._on_pomodoro_times)
        form.addRow("番茄钟专注时长", self.focus_combo)

        self.pomodoro_break_combo = QComboBox()
        self.pomodoro_break_combo.setObjectName("pomodoro_break")
        for minutes in POMODORO_BREAKS:
            self.pomodoro_break_combo.addItem(f"{minutes} 分钟", minutes)
        current_rest = int(getattr(self.config, "pomodoro_break_minutes", 5))
        self.pomodoro_break_combo.setCurrentIndex(
            max(self.pomodoro_break_combo.findData(current_rest), 0)
        )
        self.pomodoro_break_combo.currentIndexChanged.connect(self._on_pomodoro_times)
        form.addRow("番茄钟休息时长", self.pomodoro_break_combo)
        return page

    # ---------------------------------------------------------------- 系统
    # ---------------------------------------------------------------- 外观
    def _build_appearance_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        body_group = QGroupBox("火柴人躯体")
        form = QFormLayout(body_group)

        self.stick_body_check = QCheckBox("显示火柴人躯体（大头 + 身体）")
        self.stick_body_check.setObjectName("stick_body")
        self.stick_body_check.setChecked(bool(getattr(self.config, "stick_body_enabled", True)))
        self.stick_body_check.toggled.connect(self._on_stick_body)
        form.addRow(self.stick_body_check)

        self.stick_ratio_combo = QComboBox()
        self.stick_ratio_combo.setObjectName("stick_ratio")
        for ratio, label in (
            (0.6, "小巧"),
            (0.75, "偏小"),
            (0.85, "标准"),
            (1.0, "高挑"),
            (1.2, "夸张"),
        ):
            self.stick_ratio_combo.addItem(label, ratio)
        current_ratio = float(getattr(self.config, "stick_body_ratio", 0.85))
        index = self.stick_ratio_combo.findData(current_ratio)
        self.stick_ratio_combo.setCurrentIndex(index if index >= 0 else 2)
        self.stick_ratio_combo.currentIndexChanged.connect(self._on_stick_ratio)
        form.addRow("躯体比例", self.stick_ratio_combo)

        self.stick_axis_combo = QComboBox()
        self.stick_axis_combo.setObjectName("stick_spin_axis")
        self.stick_axis_combo.addItem("原地转身（Y 轴翻转）", "flip")
        self.stick_axis_combo.addItem("平面滚转（旧版风车）", "roll")
        axis_index = self.stick_axis_combo.findData(
            getattr(self.config, "stick_spin_axis", "flip")
        )
        self.stick_axis_combo.setCurrentIndex(max(axis_index, 0))
        self.stick_axis_combo.currentIndexChanged.connect(self._on_stick_axis)
        form.addRow("360° 旋转", self.stick_axis_combo)

        layout.addWidget(body_group)

        action_group = QGroupBox("随机动作")
        action_form = QFormLayout(action_group)
        self.stick_random_check = QCheckBox("空闲时随机招手 / 跳舞")
        self.stick_random_check.setObjectName("stick_random")
        self.stick_random_check.setChecked(
            bool(getattr(self.config, "stick_random_action_enabled", True))
        )
        self.stick_random_check.toggled.connect(self._on_stick_random)
        action_form.addRow(self.stick_random_check)

        self.stick_interval_combo = QComboBox()
        self.stick_interval_combo.setObjectName("stick_interval")
        for seconds, label in ((0, "关闭"), (8, "8 秒"), (12, "12 秒"), (20, "20 秒"), (30, "30 秒")):
            self.stick_interval_combo.addItem(label, seconds)
        current_interval = int(getattr(self.config, "stick_action_interval", 12))
        interval_index = self.stick_interval_combo.findData(current_interval)
        self.stick_interval_combo.setCurrentIndex(interval_index if interval_index >= 0 else 2)
        self.stick_interval_combo.currentIndexChanged.connect(self._on_stick_interval)
        action_form.addRow("动作间隔", self.stick_interval_combo)

        hint = QLabel("躯体由代码绘制，改比例/线宽不会重新加载素材；关闭后只显示大头。")
        hint.setWordWrap(True)
        action_form.addRow(hint)
        layout.addWidget(action_group)

        glass_group = QGroupBox("窗口质感")
        glass_form = QFormLayout(glass_group)
        self.glass_check = QCheckBox("半透明磨砂面板（关掉就只剩透明背景）")
        self.glass_check.setObjectName("glass")
        self.glass_check.setChecked(bool(getattr(self.config, "glass_enabled", True)))
        self.glass_check.toggled.connect(self._on_glass)
        glass_form.addRow(self.glass_check)

        self.corner_radius_combo = QComboBox()
        self.corner_radius_combo.setObjectName("corner_radius")
        for radius, label in (
            (0, "直角 0px"),
            (8, "微圆 8px"),
            (14, "标准 14px"),
            (20, "圆润 20px"),
            (28, "很圆 28px"),
        ):
            self.corner_radius_combo.addItem(label, radius)
        current_radius = int(getattr(self.config, "corner_radius", 14))
        radius_index = self.corner_radius_combo.findData(current_radius)
        self.corner_radius_combo.setCurrentIndex(radius_index if radius_index >= 0 else 2)
        self.corner_radius_combo.currentIndexChanged.connect(self._on_corner_radius)
        glass_form.addRow("圆角半径", self.corner_radius_combo)

        glass_hint = QLabel(
            "面板只画在透明背景上，不改变置顶与鼠标穿透；"
            "系统关闭透明效果或处于远程桌面时自动省略磨砂层，圆角保留。"
        )
        glass_hint.setWordWrap(True)
        glass_form.addRow(glass_hint)
        layout.addWidget(glass_group)
        layout.addStretch(1)
        return page

    # ---------------------------------------------------------------- 系统
    def _build_system_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        startup_group = QGroupBox("启动与集成")
        startup_form = QFormLayout(startup_group)

        self.autostart_check = QCheckBox("开机自启（写入当前用户启动项，无需管理员）")
        self.autostart_check.setObjectName("autostart")
        self.autostart_check.setChecked(is_enabled() or self.config.autostart)
        self.autostart_check.toggled.connect(self._on_autostart)
        startup_form.addRow(self.autostart_check)

        hotkey_hint = "、".join(
            f"{ACTION_LABELS[action]} {describe_binding(spec)}"
            for action, spec in DEFAULT_BINDINGS.items()
        )
        self.hotkeys_check = QCheckBox(f"启用全局热键（{hotkey_hint}），重启后生效")
        self.hotkeys_check.setObjectName("hotkeys")
        self.hotkeys_check.setChecked(self.config.hotkeys_enabled)
        self.hotkeys_check.toggled.connect(self._on_hotkeys)
        startup_form.addRow(self.hotkeys_check)

        self.remember_check = QCheckBox("记住两只桌宠的位置，下次启动还原")
        self.remember_check.setObjectName("remember_position")
        self.remember_check.setChecked(self.config.remember_position)
        self.remember_check.toggled.connect(self._on_remember)
        startup_form.addRow(self.remember_check)

        self.updates_check = QCheckBox("启动时检查新版本（只提示，不自动安装）")
        self.updates_check.setObjectName("check_updates")
        self.updates_check.setChecked(self.config.check_updates)
        self.updates_check.toggled.connect(self._on_check_updates)
        startup_form.addRow(self.updates_check)
        layout.addWidget(startup_group)

        window_group = QGroupBox("窗口行为")
        window_form = QFormLayout(window_group)

        self.always_on_top_check = QCheckBox("始终置顶（关闭后会被其它窗口盖住）")
        self.always_on_top_check.setObjectName("always_on_top")
        self.always_on_top_check.setChecked(bool(getattr(self.config, "always_on_top", True)))
        self.always_on_top_check.toggled.connect(self._on_always_on_top)
        window_form.addRow(self.always_on_top_check)

        self.click_through_check = QCheckBox("鼠标穿透（点击落到下层窗口）")
        self.click_through_check.setObjectName("click_through")
        self.click_through_check.setChecked(
            bool(self.runtime.windows["lei"].click_through)
        )
        self.click_through_check.toggled.connect(self._on_click_through)
        window_form.addRow(self.click_through_check)

        self.lock_check = QCheckBox("锁定位置（禁止拖动）")
        self.lock_check.setObjectName("lock_position")
        self.lock_check.setChecked(bool(self.config.lock_position))
        self.lock_check.toggled.connect(self._on_lock)
        window_form.addRow(self.lock_check)

        reset_button = QPushButton("恢复默认位置")
        reset_button.clicked.connect(self._reset_positions)
        window_form.addRow(reset_button)
        layout.addWidget(window_group)

        quiet_group = QGroupBox("免打扰时段")
        quiet_form = QFormLayout(quiet_group)
        self.quiet_check = QCheckBox("在该时段内不提醒、不弹气泡")
        self.quiet_check.setObjectName("quiet_hours")
        self.quiet_check.setChecked(bool(getattr(self.config, "quiet_hours_enabled", False)))
        self.quiet_check.toggled.connect(self._on_quiet)
        quiet_form.addRow(self.quiet_check)

        self.quiet_start_edit = QTimeEdit()
        self.quiet_start_edit.setObjectName("quiet_start")
        self.quiet_start_edit.setDisplayFormat("HH:mm")
        self.quiet_start_edit.setTime(
            QTime.fromString(str(getattr(self.config, "quiet_start", "23:00")), "HH:mm")
        )
        self.quiet_start_edit.timeChanged.connect(self._on_quiet_times)
        quiet_form.addRow("开始", self.quiet_start_edit)

        self.quiet_end_edit = QTimeEdit()
        self.quiet_end_edit.setObjectName("quiet_end")
        self.quiet_end_edit.setDisplayFormat("HH:mm")
        self.quiet_end_edit.setTime(
            QTime.fromString(str(getattr(self.config, "quiet_end", "08:00")), "HH:mm")
        )
        self.quiet_end_edit.timeChanged.connect(self._on_quiet_times)
        quiet_form.addRow("结束", self.quiet_end_edit)
        layout.addWidget(quiet_group)

        data_button = QPushButton("打开数据目录")
        data_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.base_dir())))
        )
        layout.addWidget(data_button)
        layout.addStretch(1)
        return page

    # ---------------------------------------------------------------- 关于
    def _build_about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel(f"雷余双桌宠 Windows 版 v{__version__}")
        title.setTextFormat(Qt.TextFormat.PlainText)
        font = title.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        mode = "便携版（数据写在程序目录 data\\）" if paths.is_portable() else "安装版（数据写在用户目录）"
        info = QLabel(f"运行模式：{mode}\n数据目录：{paths.base_dir()}")
        info.setTextFormat(Qt.TextFormat.PlainText)
        info.setWordWrap(True)
        layout.addWidget(info)

        notice = QLabel(COPYRIGHT_NOTICE)
        notice.setTextFormat(Qt.TextFormat.PlainText)
        notice.setWordWrap(True)
        layout.addWidget(notice)

        repo = QLabel("仓库：github.com/ncnnn/yulei-windows-desktop-pets")
        repo.setTextFormat(Qt.TextFormat.PlainText)
        repo.setWordWrap(True)
        layout.addWidget(repo)
        layout.addStretch(1)
        return page

    # ---------------------------------------------------------------- 回调
    def _persist(self) -> None:
        save_config(self.config, paths.config_path())

    def _on_volume(self, value: int) -> None:
        self.runtime.set_volume(value / 100)
        self.config.volume = max(0.0, min(value / 100, 1.0))
        self._refresh_volume_hint(value)
        self._persist()

    def _refresh_volume_hint(self, percent: int) -> None:
        """音量低于 20% 时，决战模式的 20%→70% 阶梯会被压平，需要说明。"""
        if percent < 20:
            self.volume_hint.setText(
                "⚠ 当前音量低于 20%：决战模式每句都会按当前音量播放，"
                "听不出 20%→70% 的阶梯。"
            )
        else:
            self.volume_hint.setText("决战模式会在这个音量以下逐句从 20% 升到 70%。")

    def _set_voice(self, mode: str) -> None:
        self.runtime.controller.set_voice_mode(mode)
        self.config.helium = mode == "helium"
        self._persist()

    def _on_explicit(self, checked: bool) -> None:
        self.runtime.controller.set_include_explicit(checked)
        self.config.include_explicit = checked
        self._persist()

    def _on_tilt(self, checked: bool) -> None:
        self.runtime.controller.set_tilt_enabled(checked)
        self.config.tilt_enabled = checked
        self._persist()

    def _on_crosstalk_lines(self, index: int) -> None:
        lines = int(self.crosstalk_combo.itemData(index))
        self.runtime.controller.set_crosstalk_lines(lines)
        self.config.crosstalk_lines = lines
        self._persist()

    def _on_rate(self, index: int) -> None:
        rate = float(self.rate_combo.itemData(index))
        self.runtime.set_rate(rate)
        self.config.playback_rate = rate
        self._persist()

    def _on_caption_size(self, value: int) -> None:
        setter = getattr(self.runtime, "set_caption_font_size", None)
        if callable(setter):
            setter(value)
        self.config.caption_font_size = int(value)
        self._persist()

    def _on_opacity(self, value: int) -> None:
        opacity = max(0.3, min(value / 100, 1.0))
        setter = getattr(self.runtime, "set_opacity", None)
        if callable(setter):
            setter(opacity)
        self.config.opacity = opacity
        self._persist()

    def _on_wander(self, checked: bool) -> None:
        self.config.wander_enabled = bool(checked)
        setter = getattr(self.runtime, "set_wander_enabled", None)
        if callable(setter):
            setter(
                bool(checked),
                int(getattr(self.config, "wander_interval_seconds", 45)),
            )
        self._persist()

    def _on_wander_interval(self, index: int) -> None:
        seconds = int(self.wander_interval_combo.itemData(index))
        self.config.wander_interval_seconds = seconds
        if bool(getattr(self.config, "wander_enabled", False)):
            setter = getattr(self.runtime, "set_wander_enabled", None)
            if callable(setter):
                setter(True, seconds)
        self._persist()

    def _on_overlap(self, checked: bool) -> None:
        self.config.overlap_easter_egg = bool(checked)
        setter = getattr(self.runtime, "set_overlap_easter_egg", None)
        if callable(setter):
            setter(bool(checked))
        else:
            self.runtime.controller.set_overlap_easter_egg(bool(checked))
        self._persist()

    def _on_auto_dialog_chance(self, index: int) -> None:
        self.config.auto_move_dialog_chance = int(self.auto_dialog_combo.itemData(index))
        self._apply_auto_dialog()
        self._persist()

    def _on_auto_dialog_mode(self, index: int) -> None:
        self.config.auto_move_dialog_mode = str(self.auto_dialog_mode_combo.itemData(index))
        self._apply_auto_dialog()
        self._persist()

    def _apply_auto_dialog(self) -> None:
        setter = getattr(self.runtime, "set_auto_dialog", None)
        if callable(setter):
            setter(
                int(getattr(self.config, "auto_move_dialog_chance", 0)),
                str(getattr(self.config, "auto_move_dialog_mode", "crosstalk")),
            )

    def _on_duel_effect(self, checked: bool) -> None:
        self.config.duel_effect_enabled = bool(checked)
        setter = getattr(self.runtime, "set_duel_effect_enabled", None)
        if callable(setter):
            setter(bool(checked))
        self._persist()

    def _on_stick_body(self, checked: bool) -> None:
        self.config.stick_body_enabled = bool(checked)
        setter = getattr(self.runtime, "set_stick_body_enabled", None)
        if callable(setter):
            setter(bool(checked))
        else:
            for window in self.runtime.windows.values():
                window.set_stick_body_enabled(bool(checked))
        self._persist()

    def _on_stick_random(self, checked: bool) -> None:
        self.config.stick_random_action_enabled = bool(checked)
        self._apply_stick_action_settings()
        self._persist()

    def _on_stick_interval(self, index: int) -> None:
        value = self.stick_interval_combo.itemData(index)
        self.config.stick_action_interval = int(value)
        self._apply_stick_action_settings()
        self._persist()

    def _apply_stick_action_settings(self) -> None:
        setter = getattr(self.runtime, "set_stick_action_settings", None)
        if callable(setter):
            setter(
                bool(getattr(self.config, "stick_random_action_enabled", True)),
                int(getattr(self.config, "stick_action_interval", 12)),
            )

    def _on_stick_ratio(self, index: int) -> None:
        ratio = float(self.stick_ratio_combo.itemData(index))
        self.config.stick_body_ratio = ratio
        for window in self.runtime.windows.values():
            setter = getattr(window, "set_stick_body_ratio", None)
            if callable(setter):
                setter(ratio)
        self._persist()

    def _on_stick_axis(self, index: int) -> None:
        axis = str(self.stick_axis_combo.itemData(index))
        self.config.stick_spin_axis = axis
        for window in self.runtime.windows.values():
            setter = getattr(window, "set_stick_spin_axis", None)
            if callable(setter):
                setter(axis)
        self._persist()

    def _on_glass(self, checked: bool) -> None:
        self.config.glass_enabled = bool(checked)
        self._apply_glass()
        self._persist()

    def _on_corner_radius(self, index: int) -> None:
        radius = int(self.corner_radius_combo.itemData(index))
        self.config.corner_radius = radius
        self._apply_glass()
        self._persist()

    def _apply_glass(self) -> None:
        setter = getattr(self.runtime, "set_glass", None)
        if callable(setter):
            setter(
                bool(getattr(self.config, "glass_enabled", True)),
                int(getattr(self.config, "corner_radius", 14)),
            )
            return
        from .glass import plan_glass

        plan = plan_glass(
            enabled=bool(getattr(self.config, "glass_enabled", True)),
            radius=int(getattr(self.config, "corner_radius", 14)),
        )
        for window in self.runtime.windows.values():
            window.apply_glass_plan(plan)

    def _on_hourly(self, checked: bool) -> None:
        self.config.hourly_chime = bool(checked)
        self._configure_assistant()
        self._persist()

    def _on_break_reminder(self, index: int) -> None:
        self.config.break_reminder_minutes = int(self.break_reminder_combo.itemData(index))
        self._configure_assistant()
        self._persist()

    def _on_pomodoro_times(self, _index: int) -> None:
        self.config.pomodoro_focus_minutes = int(self.focus_combo.currentData())
        self.config.pomodoro_break_minutes = int(self.pomodoro_break_combo.currentData())
        self._configure_assistant()
        self._persist()

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

    def _on_always_on_top(self, checked: bool) -> None:
        setter = getattr(self.runtime, "set_always_on_top", None)
        if callable(setter):
            setter(bool(checked))
        self.config.always_on_top = bool(checked)
        self._persist()

    def _on_quiet(self, checked: bool) -> None:
        self.config.quiet_hours_enabled = bool(checked)
        self._persist()

    def _on_quiet_times(self, _time=None) -> None:
        self.config.quiet_start = self.quiet_start_edit.time().toString("HH:mm")
        self.config.quiet_end = self.quiet_end_edit.time().toString("HH:mm")
        self._persist()

    def _on_reduce_motion(self, checked: bool) -> None:
        self.config.reduce_motion = checked
        for window in self.runtime.windows.values():
            window.set_reduce_motion(checked)
        self._persist()

    def _on_autostart(self, checked: bool) -> None:
        applied = checked
        try:
            set_enabled(checked)
        except Exception:
            applied = False
        if applied != checked:
            self.autostart_check.setChecked(applied)
        self.config.autostart = applied
        self._persist()

    def _on_hotkeys(self, checked: bool) -> None:
        self.config.hotkeys_enabled = checked
        self._persist()

    def _on_remember(self, checked: bool) -> None:
        self.config.remember_position = checked
        self._persist()

    def _on_check_updates(self, checked: bool) -> None:
        self.config.check_updates = checked
        self._persist()

    def _on_click_through(self, checked: bool) -> None:
        self.config.click_through = checked
        for role in ROLES:
            self.runtime.windows[role].set_click_through(checked)
        self._persist()

    def _on_lock(self, checked: bool) -> None:
        self.config.lock_position = checked
        for window in self.runtime.windows.values():
            window.set_locked(checked)
        self._persist()

    def _reset_positions(self) -> None:
        for role in ROLES:
            self.runtime.reset_position(role)
        self.config.lei_pos = []
        self.config.yu_pos = []
        self._persist()
