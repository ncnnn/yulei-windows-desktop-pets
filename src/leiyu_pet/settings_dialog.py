"""设置对话框：即时把控件改动应用到运行时/配置。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QPushButton,
    QSlider,
)

from .autostart import is_enabled, set_enabled
from .config import Config, save_config
from .context_menu import ROLE_NAMES
from .paths import config_path

ROLES = ("lei", "yu")
DISTANCES = ((8, "贴近"), (32, "靠近"), (80, "较远"))
SIZES = ((170, "小"), (220, "中"), (290, "大"))


class SettingsDialog(QDialog):
    def __init__(self, runtime, config: Config) -> None:
        super().__init__()
        self.runtime = runtime
        self.config = config
        self.setWindowTitle("雷余双桌宠设置")

        layout = QFormLayout(self)

        volume = QSlider()
        volume.setRange(0, 100)
        volume.setValue(round(runtime.volume * 100))
        volume.valueChanged.connect(lambda v: runtime.set_volume(v / 100))
        layout.addRow("音量", volume)

        distance = QComboBox()
        for value, label in DISTANCES:
            distance.addItem(f"{label}（{value}）", value)
        current = round(runtime.controller.proximity.distance)
        distance.setCurrentIndex(max(distance.findData(current), 0))
        distance.currentIndexChanged.connect(
            lambda index: runtime.set_distance(distance.itemData(index))
        )
        layout.addRow("歪头距离", distance)

        for role in ROLES:
            size_box = QComboBox()
            for value, label in SIZES:
                size_box.addItem(label, value)
            size_box.setCurrentIndex(
                max(size_box.findData(runtime.windows[role].pet_size), 1)
            )
            size_box.currentIndexChanged.connect(
                lambda index, r=role, box=size_box: runtime.set_pet_size(
                    r, box.itemData(index)
                )
            )
            layout.addRow(f"{ROLE_NAMES[role]}大小", size_box)

        tilt = QCheckBox("靠近时互相歪头")
        tilt.setChecked(runtime.controller.tilt_enabled)
        tilt.toggled.connect(lambda checked: runtime.controller.set_tilt_enabled(checked))
        layout.addRow(tilt)

        voice = QComboBox()
        voice.addItem("原声", "normal")
        voice.addItem("1.5倍氦气版", "helium")
        voice.setCurrentIndex(max(voice.findData(runtime.controller.voice_mode), 0))
        voice.currentIndexChanged.connect(
            lambda index: runtime.controller.set_voice_mode(voice.itemData(index))
        )
        layout.addRow("声音模式", voice)

        explicit = QCheckBox("显示粗口台词（第17段）")
        explicit.setChecked(runtime.controller.include_explicit)
        explicit.toggled.connect(
            lambda checked: runtime.controller.set_include_explicit(checked)
        )
        layout.addRow(explicit)

        autostart = QCheckBox("开机自启")
        autostart.setChecked(is_enabled() or config.autostart)
        autostart.toggled.connect(self._on_autostart)
        layout.addRow(autostart)

        click_through = QCheckBox("鼠标穿透（点击穿透到桌面）")
        click_through.setChecked(runtime.windows["lei"].click_through())
        click_through.toggled.connect(self._on_click_through)
        layout.addRow(click_through)

        lock = QCheckBox("锁定位置（由主程序读取生效）")
        lock.setChecked(config.lock_position)
        lock.toggled.connect(self._on_lock)
        layout.addRow(lock)

        ok = QPushButton("确定")
        ok.clicked.connect(self.accept)
        layout.addRow(ok)

    def _on_autostart(self, checked: bool) -> None:
        set_enabled(checked)
        self.config.autostart = checked
        save_config(self.config, config_path())

    def _on_click_through(self, checked: bool) -> None:
        for role in ROLES:
            self.runtime.windows[role].set_click_through(checked)

    def _on_lock(self, checked: bool) -> None:
        self.config.lock_position = checked
        save_config(self.config, config_path())
