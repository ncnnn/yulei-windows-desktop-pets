"""设置中心：分页（声音 / 互动 / 系统 / 关于），控件改动即时生效并落盘。

安装版与便携版共用同一套代码，所以两边的设置项完全一致；差异只体现在
「关于」页显示的数据目录（``%LOCALAPPDATA%`` 还是 exe 同级 ``data``）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
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
    QVBoxLayout,
    QWidget,
)

from . import __version__, paths
from .autostart import is_enabled, set_enabled
from .config import Config, save_config
from .context_menu import ROLE_NAMES
from .crosstalk import LINE_PRESETS
from .hotkeys import ACTION_LABELS, DEFAULT_BINDINGS, describe_binding

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

        self.click_through_check = QCheckBox("鼠标穿透（点击落到下层窗口）")
        self.click_through_check.setObjectName("click_through")
        self.click_through_check.setChecked(self.runtime.windows["lei"].click_through())
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
        self._persist()

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
