"""SettingsDialog 测试（offscreen，不弹真实窗口）。"""

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_STUB_ROOT = Path(tempfile.mkdtemp(prefix="leiyu-settings-stub-"))


def _build_stub_modules():
    config_mod = types.ModuleType("leiyu_pet.config")

    class Config:
        def __init__(self, **kwargs):
            self.volume = 0.65
            self.distance = 32
            self.tilt_enabled = True
            self.helium = False
            self.include_explicit = False
            self.autostart = False
            self.click_through = False
            self.lock_position = False
            self.lei_visible = True
            self.yu_visible = True
            self.crosstalk_lines = 6
            self.remember_position = True
            self.lei_pos = []
            self.yu_pos = []
            self.hotkeys_enabled = True
            self.check_updates = True
            self.reduce_motion = False
            self.frosted_ui_enabled = True
            self.version = 2
            self._saved = []
            for key, value in kwargs.items():
                setattr(self, key, value)

    def save_config(cfg, path):
        cfg._saved.append(path)

    config_mod.Config = Config
    config_mod.save_config = save_config

    paths_mod = types.ModuleType("leiyu_pet.paths")
    paths_mod.assets_dir = lambda: _STUB_ROOT / "assets"
    paths_mod.assets_store_dir = lambda: _STUB_ROOT / "assets"
    paths_mod.config_path = lambda: _STUB_ROOT / "config.json"
    paths_mod.base_dir = lambda: _STUB_ROOT
    paths_mod.is_portable = lambda: False

    autostart_mod = types.ModuleType("leiyu_pet.autostart")
    autostart_mod._state = {"enabled": False}

    def is_enabled(exe_path=None):
        return autostart_mod._state["enabled"]

    def set_enabled(enabled, exe_path=None):
        autostart_mod._state["enabled"] = bool(enabled)
        return True

    def self_check_requested_but_missing(config_autostart, exe_path=None):
        return bool(config_autostart) and not autostart_mod._state["enabled"]

    autostart_mod.is_enabled = is_enabled
    autostart_mod.set_enabled = set_enabled
    autostart_mod.self_check_requested_but_missing = (
        self_check_requested_but_missing
    )

    return {
        "leiyu_pet.config": config_mod,
        "leiyu_pet.paths": paths_mod,
        "leiyu_pet.autostart": autostart_mod,
    }


_STUBS = _build_stub_modules()
_SAVED_MODULES = {}
for _name, _mod in _STUBS.items():
    _SAVED_MODULES[_name] = sys.modules.get(_name)
    sys.modules[_name] = _mod

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
)

from leiyu_pet import __version__  # noqa: E402
from leiyu_pet.autostart import is_enabled  # noqa: E402
from leiyu_pet.config import Config  # noqa: E402
from leiyu_pet.settings_dialog import COPYRIGHT_NOTICE, ROLES, SettingsDialog  # noqa: E402

# 恢复 sys.modules，避免污染全局，影响依赖真实模块的其他测试
for _name, _mod in _STUBS.items():
    if _SAVED_MODULES[_name] is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _SAVED_MODULES[_name]

# settings_dialog 已在本文件的桩环境下导入；从缓存移除，后续测试会拿到
# 绑定真实 config/paths 的新模块（否则 save_config 仍是桩函数）。
sys.modules.pop("leiyu_pet.settings_dialog", None)


class FakeWindow:
    def __init__(self, visible=True, size=220):
        self._visible = visible
        self.pet_size = size
        self._click_through = False
        self.locked = None
        self.reduce_motion = None

    def isVisible(self):
        return self._visible

    def setVisible(self, value):
        self._visible = bool(value)

    def set_pet_size(self, size):
        self.pet_size = size

    def set_click_through(self, value):
        self._click_through = bool(value)

    @property
    def click_through(self):
        return self._click_through

    def set_locked(self, value):
        self.locked = bool(value)

    def set_reduce_motion(self, value):
        self.reduce_motion = bool(value)



class FakeController:
    def __init__(self):
        self.voice_mode = "normal"
        self.include_explicit = False
        self.tilt_enabled = True
        self.crosstalk_lines = 6
        self.playback_rate = 1.0
        self.overlap_enabled = False
        self.proximity = types.SimpleNamespace(distance=32.0)
        self.calls = []

    def set_overlap_easter_egg(self, value):
        self.calls.append(("set_overlap_easter_egg", value))
        self.overlap_enabled = bool(value)

    def set_voice_mode(self, mode):
        self.calls.append(("set_voice_mode", mode))
        self.voice_mode = mode

    def set_include_explicit(self, value):
        self.calls.append(("set_include_explicit", value))
        self.include_explicit = bool(value)

    def set_tilt_enabled(self, value):
        self.calls.append(("set_tilt_enabled", value))
        self.tilt_enabled = bool(value)

    def set_crosstalk_lines(self, value):
        self.calls.append(("set_crosstalk_lines", value))
        self.crosstalk_lines = value

    def set_volume(self, value):
        self.calls.append(("set_volume", value))

    def set_rate(self, rate):
        self.calls.append(("set_rate", rate))
        self.playback_rate = rate

    def set_distance(self, value):
        self.calls.append(("set_distance", value))
        self.proximity.distance = value

    def update_proximity(self):
        self.calls.append(("update_proximity",))
        return True


class FakeRuntime:
    def __init__(self, volume=0.65):
        self.volume = volume
        self.windows = {
            "lei": FakeWindow(True, 220),
            "yu": FakeWindow(True, 220),
        }
        self.controller = FakeController()
        self.calls = []
        self.frosted = None
        self.muted = False

    def set_volume(self, value):
        self.volume = min(max(float(value), 0.0), 1.0)
        self.calls.append(("set_volume", self.volume))

    def set_muted(self, enabled):
        self.muted = bool(enabled)
        self.calls.append(("set_muted", self.muted))

    def set_rate(self, rate):
        self.calls.append(("set_rate", rate))
        self.controller.playback_rate = rate

    def set_distance(self, value):
        self.calls.append(("set_distance", value))

    def set_pet_size(self, role, size):
        self.windows[role].set_pet_size(size)
        self.calls.append(("set_pet_size", role, size))

    def set_frosted_ui(self, enabled):
        self.frosted = bool(enabled)
        self.calls.append(("set_frosted_ui", self.frosted))

    def set_role_visible(self, role, visible):
        self.windows[role].setVisible(visible)
        self.calls.append(("set_role_visible", role, visible))

    def show_all(self):
        for role in ROLES:
            self.set_role_visible(role, True)
        self.calls.append(("show_all",))

    def toggle_role(self, role):
        self.set_role_visible(role, not self.windows[role].isVisible())

    def reset_position(self, role):
        self.calls.append(("reset_position", role))

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def app():
    existing = QApplication.instance()
    application = existing if existing is not None else QApplication([])
    yield application


def _find(dialog, name, kind):
    widget = dialog.findChild(kind, name)
    assert widget is not None, f"{kind.__name__} {name!r} not found"
    return widget


def _slider(dialog, name):
    return _find(dialog, name, QSlider)


def _combo(dialog, name):
    return _find(dialog, name, QComboBox)


def _check(dialog, name):
    return _find(dialog, name, QCheckBox)


def test_tabs_and_core_widgets_exist(app):
    dialog = SettingsDialog(FakeRuntime(), Config())

    titles = [dialog._tabs.tabText(i) for i in range(dialog._tabs.count())]
    assert titles == ["声音", "互动", "外观", "系统", "关于"]

    assert _slider(dialog, "volume") is not None
    assert _combo(dialog, "voice") is not None
    assert _combo(dialog, "distance") is not None
    assert _combo(dialog, "size_lei") is not None
    assert _combo(dialog, "size_yu") is not None
    assert _combo(dialog, "crosstalk_lines") is not None
    for name in (
        "explicit",
        "tilt",
        "reduce_motion",
        "autostart",
        "hotkeys",
        "remember_position",
        "check_updates",
        "click_through",
        "lock_position",
    ):
        assert _check(dialog, name) is not None


def test_about_page_states_copyright(app):
    dialog = SettingsDialog(FakeRuntime(), Config())
    labels = " ".join(
        label.text() for label in dialog._tabs.widget(4).findChildren(QLabel)
    )
    assert "MIT" in COPYRIGHT_NOTICE
    assert "原作者" in COPYRIGHT_NOTICE or "原权利人" in COPYRIGHT_NOTICE
    assert "非商业" in COPYRIGHT_NOTICE or "不用于商业" in COPYRIGHT_NOTICE
    assert "yuhanfu513-ops/leiyu-desktop-pets" in COPYRIGHT_NOTICE
    assert "yuhanfu513-ops/leiyu-desktop-pets" in labels


def test_volume_slider(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.calls.clear()

    _slider(dialog, "volume").setValue(50)
    assert ("set_volume", 0.5) in runtime.calls


def test_distance_combo(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.calls.clear()

    combo = _combo(dialog, "distance")
    combo.setCurrentIndex(combo.findData(8))
    assert ("set_distance", 8) in runtime.calls


def test_size_combo(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.calls.clear()

    combo = _combo(dialog, "size_lei")
    combo.setCurrentIndex(combo.findData(170))
    assert ("set_pet_size", "lei", 170) in runtime.calls


def test_voice_combo(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.calls.clear()

    combo = _combo(dialog, "voice")
    combo.setCurrentIndex(combo.findData("helium"))
    assert runtime.controller.voice_mode == "helium"


def test_tilt_checkbox(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.controller.calls.clear()

    _check(dialog, "tilt").setChecked(False)
    assert runtime.controller.tilt_enabled is False


def test_explicit_checkbox(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.controller.calls.clear()

    _check(dialog, "explicit").setChecked(True)
    assert runtime.controller.include_explicit is True


def test_crosstalk_lines_combo(app):
    runtime = FakeRuntime()
    config = Config()
    dialog = SettingsDialog(runtime, config)

    combo = _combo(dialog, "crosstalk_lines")
    combo.setCurrentIndex(combo.findData(20))
    assert runtime.controller.crosstalk_lines == 20
    assert config.crosstalk_lines == 20
    assert config._saved


def test_crosstalk_lines_presets_include_twenty(app):
    """默认一次说满 20 句，不用每次去菜单里改。"""
    dialog = SettingsDialog(FakeRuntime(), Config())
    combo = _combo(dialog, "crosstalk_lines")

    assert combo.findData(20) >= 0
    assert combo.findData(8) >= 0


def test_reduce_motion_applies_to_windows(app):
    runtime = FakeRuntime()
    config = Config()
    dialog = SettingsDialog(runtime, config)

    _check(dialog, "reduce_motion").setChecked(True)
    assert runtime.windows["lei"].reduce_motion is True
    assert runtime.windows["yu"].reduce_motion is True
    assert config.reduce_motion is True


def test_autostart_checkbox_saves(app):
    runtime = FakeRuntime()
    config = Config()
    dialog = SettingsDialog(runtime, config)

    _check(dialog, "autostart").setChecked(True)
    assert is_enabled() is True
    assert config.autostart is True
    assert config._saved


def test_hotkeys_and_update_toggles_persist(app):
    runtime = FakeRuntime()
    config = Config()
    dialog = SettingsDialog(runtime, config)

    _check(dialog, "hotkeys").setChecked(False)
    _check(dialog, "check_updates").setChecked(False)
    _check(dialog, "remember_position").setChecked(False)

    assert config.hotkeys_enabled is False
    assert config.check_updates is False
    assert config.remember_position is False
    assert len(config._saved) >= 3


def test_click_through_checkbox(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())

    _check(dialog, "click_through").setChecked(True)
    assert runtime.windows["lei"].click_through is True
    assert runtime.windows["yu"].click_through is True


def test_lock_checkbox_applies_and_saves(app):
    runtime = FakeRuntime()
    config = Config()
    dialog = SettingsDialog(runtime, config)

    _check(dialog, "lock_position").setChecked(True)
    assert config.lock_position is True
    assert runtime.windows["lei"].locked is True
    assert config._saved


def test_volume_hint_warns_below_battle_ladder(app):
    dialog = SettingsDialog(FakeRuntime(), Config())

    dialog._on_volume(10)
    assert "音量偏低" in dialog.volume_hint.text()

    dialog._on_volume(60)
    assert "20%" in dialog.volume_hint.text()
    assert "音量偏低" not in dialog.volume_hint.text()


def test_interaction_page_has_stage3_controls(app):
    dialog = SettingsDialog(FakeRuntime(), Config())
    assert _combo(dialog, "auto_dialog_chance") is not None
    assert _combo(dialog, "auto_dialog_mode") is not None
    assert _check(dialog, "duel_effect") is not None


def test_appearance_page_has_frosted_control(app):
    runtime = FakeRuntime()
    config = Config()
    dialog = SettingsDialog(runtime, config)

    box = _check(dialog, "frosted_ui")
    assert box is not None
    assert box.isChecked() is True

    box.setChecked(False)
    assert config.frosted_ui_enabled is False
    assert runtime.frosted is False
    assert config._saved

    box.setChecked(True)
    assert runtime.frosted is True


def test_settings_dialog_is_frameless_and_translucent(app):
    """磨砂设置窗口：无边框 + 半透明底，靠自绘圆角面板撑起观感。"""
    dialog = SettingsDialog(FakeRuntime(), Config())
    flags = dialog.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


# ------------------------------------------------------------ 2.1.2 界面重做


def test_window_title_uses_the_new_product_name(app):
    dialog = SettingsDialog(FakeRuntime(), Config())
    assert "鱼雷双桌宠" in dialog.windowTitle()
    assert "雷余" not in dialog.windowTitle()


def test_header_shows_only_settings_and_version(app):
    """标题行不再重复产品名：界面里只留「设置 + 版本」。"""
    dialog = SettingsDialog(FakeRuntime(), Config())

    assert dialog._title.text() == "设置"
    assert "鱼雷双桌宠" not in dialog._title.text()
    assert "鱼雷双桌宠" not in dialog._subtitle.text()
    assert __version__ in dialog._subtitle.text()


def test_every_tab_is_scrollable(app):
    """内容多的页签要靠滚动消化，不能把窗口顶到屏幕外。"""
    dialog = SettingsDialog(FakeRuntime(), Config())
    for index in range(dialog._tabs.count()):
        assert isinstance(dialog._tabs.widget(index), QScrollArea)


def test_inline_buttons_are_left_aligned_and_not_default(app):
    dialog = SettingsDialog(FakeRuntime(), Config())
    buttons = dialog.findChildren(QPushButton, "inline_action")
    assert buttons
    for button in buttons:
        assert button.autoDefault() is False
        # 外层是 HBox 容器，右侧有弹簧，按钮不会被表单拉成整行宽
        layout = button.parentWidget().layout()
        assert isinstance(layout, QHBoxLayout)
        assert layout.count() == 2


def test_close_button_is_localised(app):
    dialog = SettingsDialog(FakeRuntime(), Config())
    close = dialog._buttons.button(QDialogButtonBox.StandardButton.Close)
    assert close is not None
    assert close.text() == "关闭"


def test_pages_are_grouped_into_cards(app):
    """每页都要有卡片分组，否则控件会散在大片空白里。"""
    from PySide6.QtWidgets import QGroupBox

    dialog = SettingsDialog(FakeRuntime(), Config())
    for index in range(dialog._tabs.count()):
        page = dialog._tabs.widget(index).widget()
        assert page.findChildren(QGroupBox), f"第 {index} 页没有分组卡片"
